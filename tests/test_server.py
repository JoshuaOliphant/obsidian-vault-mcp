# ABOUTME: Integration tests for the MCP server tools.
# ABOUTME: Tests each tool end-to-end using a temporary vault fixture.

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

import obsidian_vault_mcp.server as server_module
from obsidian_vault_mcp.config import VaultConfig
from obsidian_vault_mcp.server import (
    find_broken_links,
    find_orphaned_notes,
    get_backlinks,
    get_note_info,
    get_outgoing_links,
    vault_stats,
)
from obsidian_vault_mcp.vault_index import VaultIndex


@pytest.fixture(autouse=True)
def _reset_server_index():
    """Reset the server's global index before each test."""
    server_module._index = None
    yield
    server_module._index = None


@pytest.fixture
def vault_dir(tmp_path):
    """Create a realistic mini-vault for integration tests."""
    journal = tmp_path / "journal"
    journal.mkdir()
    areas = tmp_path / "areas"
    areas.mkdir()

    (journal / "2026-02-28.md").write_text(
        "---\ntags: [daily]\n---\n# Friday\n\n"
        "Drew [[Queen of Cups]] today.\n"
        "Met with [[Martin]] about the project.\n"
        "See [[Missing Page]] for details.\n"
    )
    (journal / "2026-02-27.md").write_text(
        "---\ntags: [daily]\n---\n# Thursday\n\n"
        "Continued reading about [[Queen of Cups]].\n"
    )
    (areas / "Queen of Cups.md").write_text(
        "---\ntags: [tarot]\n---\n# Queen of Cups\n\nA card of emotional depth.\n"
    )
    (areas / "Martin.md").write_text(
        "---\ntags: [people]\n---\n# Martin\n\nColleague.\n"
    )
    (areas / "orphan-note.md").write_text("# Orphan\n\nNobody links here.\n")

    return tmp_path


@pytest.fixture
def configured_index(vault_dir):
    """Set up VaultIndex pointing at the test vault and inject into server."""
    config = VaultConfig(
        vault_path=vault_dir,
        scan_dirs=["journal", "areas"],
        exclude_patterns=[],
        cache_ttl=300,
    )
    index = VaultIndex(config)
    server_module._index = index
    return index


class TestGetBacklinks:
    def test_returns_backlinks_with_context(self, configured_index):
        result = get_backlinks("Queen of Cups")
        assert len(result) == 2
        sources = {r["source_file"] for r in result}
        assert "journal/2026-02-28.md" in sources
        assert "journal/2026-02-27.md" in sources
        # Context lines should mention the card
        for r in result:
            assert "Queen of Cups" in r["context_line"]

    def test_single_backlink(self, configured_index):
        result = get_backlinks("Martin")
        assert len(result) == 1
        assert result[0]["source_file"] == "journal/2026-02-28.md"

    def test_no_backlinks(self, configured_index):
        result = get_backlinks("orphan-note")
        assert result == []


class TestGetOutgoingLinks:
    def test_returns_outgoing(self, configured_index):
        result = get_outgoing_links("2026-02-28")
        assert "Queen of Cups" in result
        assert "Martin" in result
        assert "Missing Page" in result

    def test_no_outgoing(self, configured_index):
        result = get_outgoing_links("orphan-note")
        assert result == []

    def test_nonexistent_note(self, configured_index):
        result = get_outgoing_links("does-not-exist")
        assert result == []


class TestFindBrokenLinks:
    def test_finds_broken_link(self, configured_index):
        result = find_broken_links()
        targets = {r["broken_target"] for r in result}
        assert "Missing Page" in targets

    def test_broken_link_has_location(self, configured_index):
        result = find_broken_links()
        missing = [r for r in result if r["broken_target"] == "Missing Page"]
        assert len(missing) == 1
        assert missing[0]["source_file"] == "journal/2026-02-28.md"
        assert missing[0]["line_number"] > 0


class TestFindOrphanedNotes:
    def test_finds_orphans(self, configured_index):
        result = find_orphaned_notes()
        assert "areas/orphan-note.md" in result

    def test_linked_notes_not_orphaned(self, configured_index):
        result = find_orphaned_notes()
        orphan_stems = {Path(p).stem for p in result}
        assert "Queen of Cups" not in orphan_stems
        assert "Martin" not in orphan_stems


class TestGetNoteInfo:
    def test_returns_metadata(self, configured_index):
        result = get_note_info("Queen of Cups")
        assert result["outgoing_count"] == 0
        assert result["incoming_count"] == 2
        assert "tarot" in result["tags"]
        assert result["word_count"] > 0

    def test_note_not_found(self, configured_index):
        result = get_note_info("nonexistent")
        assert "error" in result


class TestVaultStats:
    def test_returns_summary(self, configured_index):
        result = vault_stats()
        assert result["total_files"] == 5
        assert result["broken_links"] >= 1
        assert result["orphaned_notes"] >= 1
        assert result["unique_tags"] > 0
        assert result["backlink_targets"] > 0
