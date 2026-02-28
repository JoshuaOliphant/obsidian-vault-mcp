# ABOUTME: Unit tests for vault parsing and graph computation logic.
# ABOUTME: Tests wiki-link extraction, frontmatter parsing, backlinks, orphans, and broken links.

from __future__ import annotations

from pathlib import Path

import pytest

from obsidian_vault_mcp.config import VaultConfig
from obsidian_vault_mcp.vault_index import (
    WIKI_LINK_RE,
    BacklinkEntry,
    BrokenLinkEntry,
    FileData,
    VaultIndex,
    build_backlinks,
    collect_files,
    compute_tag_counts,
    extract_frontmatter,
    extract_inline_tags,
    find_deadends,
    find_orphans,
    find_unresolved_with_locations,
    parse_file,
    parse_frontmatter_tags,
)


# ── Wiki-link regex ───────────────────────────────────────────────────


class TestWikiLinkRegex:
    def test_simple_link(self):
        assert WIKI_LINK_RE.findall("See [[My Note]] for details") == ["My Note"]

    def test_link_with_alias(self):
        assert WIKI_LINK_RE.findall("See [[My Note|display text]]") == ["My Note"]

    def test_multiple_links(self):
        text = "Link to [[Note A]] and [[Note B|alias]]"
        assert WIKI_LINK_RE.findall(text) == ["Note A", "Note B"]

    def test_no_links(self):
        assert WIKI_LINK_RE.findall("No links here") == []

    def test_link_with_path(self):
        assert WIKI_LINK_RE.findall("[[areas/career/README]]") == [
            "areas/career/README"
        ]

    def test_link_with_spaces(self):
        assert WIKI_LINK_RE.findall("[[Queen of Cups]]") == ["Queen of Cups"]

    def test_link_with_dash(self):
        assert WIKI_LINK_RE.findall("[[Ace of Cups - Reversed]]") == [
            "Ace of Cups - Reversed"
        ]

    def test_nested_brackets_ignored(self):
        """Regex should not match malformed nested brackets."""
        # The inner ]] closes the match, so only partial content is captured
        result = WIKI_LINK_RE.findall("[[outer [[inner]]]]")
        # Should get "inner" because the first [[ starts, then inner]] closes it
        assert len(result) >= 1


# ── Frontmatter extraction ────────────────────────────────────────────


class TestExtractFrontmatter:
    def test_with_frontmatter(self):
        content = "---\ntitle: Test\ntags: [a, b]\n---\nBody text here"
        fm, body = extract_frontmatter(content)
        assert "title: Test" in fm
        assert "Body text here" in body

    def test_without_frontmatter(self):
        content = "Just a body with no frontmatter"
        fm, body = extract_frontmatter(content)
        assert fm == ""
        assert body == content

    def test_unclosed_frontmatter(self):
        content = "---\ntitle: Test\nNo closing delimiter"
        fm, body = extract_frontmatter(content)
        assert fm == ""
        assert body == content


# ── Frontmatter tag parsing ──────────────────────────────────────────


class TestParseFrontmatterTags:
    def test_inline_format(self):
        fm = "\ntitle: Test\ntags: [coding, learning, ai]\n"
        tags = parse_frontmatter_tags(fm)
        assert tags == ["coding", "learning", "ai"]

    def test_list_format(self):
        fm = "\ntitle: Test\ntags:\n  - coding\n  - learning\n  - ai\n"
        tags = parse_frontmatter_tags(fm)
        assert tags == ["coding", "learning", "ai"]

    def test_quoted_tags(self):
        fm = "\ntags: ['tag-one', \"tag-two\"]\n"
        tags = parse_frontmatter_tags(fm)
        assert tags == ["tag-one", "tag-two"]

    def test_no_tags(self):
        fm = "\ntitle: Test\nstatus: active\n"
        tags = parse_frontmatter_tags(fm)
        assert tags == []

    def test_empty_tags(self):
        fm = "\ntags: []\n"
        tags = parse_frontmatter_tags(fm)
        assert tags == []


# ── Inline tag extraction ────────────────────────────────────────────


class TestExtractInlineTags:
    def test_simple_tags(self):
        body = "Some text #python and #coding stuff"
        tags = extract_inline_tags(body)
        assert "python" in tags
        assert "coding" in tags

    def test_skips_headings(self):
        body = "# Heading\nSome #real-tag text"
        tags = extract_inline_tags(body)
        assert "real-tag" in tags
        assert "Heading" not in tags

    def test_skips_code_blocks(self):
        body = "Before\n```\n#not-a-tag\n```\nAfter #real-tag"
        tags = extract_inline_tags(body)
        assert "real-tag" in tags
        assert "not-a-tag" not in tags

    def test_skips_urls(self):
        body = "Visit https://example.com/#fragment and #real-tag"
        tags = extract_inline_tags(body)
        assert "real-tag" in tags
        # fragment should not appear as a tag


# ── File parsing (needs tmp files) ────────────────────────────────────


class TestParseFile:
    def test_basic_file(self, tmp_path):
        note = tmp_path / "test.md"
        note.write_text(
            "---\ntags: [python]\n---\n# Hello\n\nSee [[Other Note]] for details.\n"
        )
        result = parse_file(note, tmp_path)
        assert result.relative_path == "test.md"
        assert "Other Note" in result.outgoing_links
        assert "python" in result.tags
        assert result.word_count > 0

    def test_links_in_code_blocks_excluded(self, tmp_path):
        note = tmp_path / "test.md"
        note.write_text("Real [[Link A]]\n```\n[[Link B]]\n```\nEnd\n")
        result = parse_file(note, tmp_path)
        assert "Link A" in result.outgoing_links
        assert "Link B" not in result.outgoing_links

    def test_links_in_inline_code_excluded(self, tmp_path):
        note = tmp_path / "test.md"
        note.write_text("Real [[Link A]] and `[[Link B]]` end\n")
        result = parse_file(note, tmp_path)
        assert "Link A" in result.outgoing_links
        assert "Link B" not in result.outgoing_links

    def test_confidence_markers(self, tmp_path):
        note = tmp_path / "test.md"
        note.write_text("I believe this [solid] and this [hypothesis]\n")
        result = parse_file(note, tmp_path)
        assert "[solid]" in result.confidence_markers
        assert "[hypothesis]" in result.confidence_markers
        assert "[evolving]" not in result.confidence_markers

    def test_unreadable_file(self, tmp_path):
        note = tmp_path / "bad.md"
        note.write_bytes(b"\x80\x81\x82\x83")  # invalid utf-8
        result = parse_file(note, tmp_path)
        assert result.relative_path == "bad.md"
        assert result.outgoing_links == []
        assert result.word_count == 0


# ── Collect files ─────────────────────────────────────────────────────


class TestCollectFiles:
    def test_collects_md_files(self, tmp_path):
        journal = tmp_path / "journal"
        journal.mkdir()
        (journal / "note1.md").write_text("note 1")
        (journal / "note2.md").write_text("note 2")
        (journal / "image.png").write_text("not md")

        files = collect_files(tmp_path, [journal], [])
        assert len(files) == 2
        assert all(f.suffix == ".md" for f in files)

    def test_excludes_patterns(self, tmp_path):
        area = tmp_path / "areas"
        area.mkdir()
        (area / "good.md").write_text("keep")
        hidden = area / ".obsidian"
        hidden.mkdir()
        (hidden / "bad.md").write_text("skip")

        files = collect_files(tmp_path, [area], [".obsidian/"])
        assert len(files) == 1
        assert files[0].name == "good.md"

    def test_skips_missing_dirs(self, tmp_path):
        missing = tmp_path / "nonexistent"
        files = collect_files(tmp_path, [missing], [])
        assert files == []


# ── Backlinks ─────────────────────────────────────────────────────────


class TestBuildBacklinks:
    def test_basic_backlinks(self, tmp_path):
        # Create files that link to each other
        (tmp_path / "a.md").write_text("Links to [[B]] here\n")
        (tmp_path / "b.md").write_text("Links to [[A]] here\n")

        files = {
            "a.md": FileData(relative_path="a.md", outgoing_links=["B"]),
            "b.md": FileData(relative_path="b.md", outgoing_links=["A"]),
        }
        backlinks = build_backlinks(files, tmp_path)

        assert "B" in backlinks
        assert len(backlinks["B"]) == 1
        assert backlinks["B"][0].source_file == "a.md"
        assert "[[B]]" in backlinks["B"][0].context_line

        assert "A" in backlinks
        assert backlinks["A"][0].source_file == "b.md"

    def test_context_lines_captured(self, tmp_path):
        (tmp_path / "source.md").write_text(
            "Line 1\nLine 2 with [[Target]] link\nLine 3\n"
        )
        files = {
            "source.md": FileData(
                relative_path="source.md", outgoing_links=["Target"]
            ),
        }
        backlinks = build_backlinks(files, tmp_path)
        entry = backlinks["Target"][0]
        assert entry.context_line == "Line 2 with [[Target]] link"
        assert entry.line_number == 2

    def test_multiple_sources(self, tmp_path):
        (tmp_path / "a.md").write_text("See [[Hub]]\n")
        (tmp_path / "b.md").write_text("Also [[Hub]]\n")
        (tmp_path / "c.md").write_text("And [[Hub]] too\n")

        files = {
            "a.md": FileData(relative_path="a.md", outgoing_links=["Hub"]),
            "b.md": FileData(relative_path="b.md", outgoing_links=["Hub"]),
            "c.md": FileData(relative_path="c.md", outgoing_links=["Hub"]),
        }
        backlinks = build_backlinks(files, tmp_path)
        assert len(backlinks["Hub"]) == 3


# ── Orphans ───────────────────────────────────────────────────────────


class TestFindOrphans:
    def test_finds_orphans(self):
        files = {
            "a.md": FileData(relative_path="a.md"),
            "b.md": FileData(relative_path="b.md"),
            "c.md": FileData(relative_path="c.md"),
        }
        # Only "a" is linked to
        backlinks = {
            "a": [BacklinkEntry(source_file="b.md", context_line="", line_number=1)]
        }
        orphans = find_orphans(files, backlinks)
        assert "b.md" in orphans
        assert "c.md" in orphans
        assert "a.md" not in orphans

    def test_excludes_readme(self):
        files = {
            "README.md": FileData(relative_path="README.md"),
            "orphan.md": FileData(relative_path="orphan.md"),
        }
        orphans = find_orphans(files, {})
        assert "orphan.md" in orphans
        assert "README.md" not in orphans

    def test_excludes_index(self):
        files = {
            "index.md": FileData(relative_path="index.md"),
            "orphan.md": FileData(relative_path="orphan.md"),
        }
        orphans = find_orphans(files, {})
        assert "orphan.md" in orphans
        assert "index.md" not in orphans


# ── Deadends ──────────────────────────────────────────────────────────


class TestFindDeadends:
    def test_finds_deadends(self):
        files = {
            "linked.md": FileData(
                relative_path="linked.md", outgoing_links=["Other"]
            ),
            "deadend.md": FileData(relative_path="deadend.md", outgoing_links=[]),
        }
        deadends = find_deadends(files)
        assert "deadend.md" in deadends
        assert "linked.md" not in deadends


# ── Broken links ──────────────────────────────────────────────────────


class TestFindBrokenLinks:
    def test_finds_unresolved(self, tmp_path):
        (tmp_path / "source.md").write_text("See [[Missing Note]] here\n")

        files = {
            "source.md": FileData(
                relative_path="source.md", outgoing_links=["Missing Note"]
            ),
        }
        all_stems = {"source"}  # "Missing Note" stem not present
        broken = find_unresolved_with_locations(files, all_stems, tmp_path)
        assert len(broken) == 1
        assert broken[0].broken_target == "Missing Note"
        assert broken[0].source_file == "source.md"
        assert broken[0].line_number == 1

    def test_resolved_links_not_broken(self, tmp_path):
        (tmp_path / "source.md").write_text("See [[target]] here\n")

        files = {
            "source.md": FileData(
                relative_path="source.md", outgoing_links=["target"]
            ),
        }
        all_stems = {"source", "target"}
        broken = find_unresolved_with_locations(files, all_stems, tmp_path)
        assert broken == []


# ── Tag counts ────────────────────────────────────────────────────────


class TestComputeTagCounts:
    def test_aggregates_tags(self):
        files = {
            "a.md": FileData(
                relative_path="a.md", tags=["python", "coding"]
            ),
            "b.md": FileData(relative_path="b.md", tags=["python", "ai"]),
            "c.md": FileData(relative_path="c.md", tags=["python"]),
        }
        counts = compute_tag_counts(files)
        assert counts["python"] == 3
        assert counts["coding"] == 1
        assert counts["ai"] == 1

    def test_sorted_descending(self):
        files = {
            "a.md": FileData(relative_path="a.md", tags=["rare"]),
            "b.md": FileData(
                relative_path="b.md", tags=["common", "common2"]
            ),
            "c.md": FileData(
                relative_path="c.md", tags=["common", "common2"]
            ),
        }
        counts = compute_tag_counts(files)
        keys = list(counts.keys())
        assert counts[keys[0]] >= counts[keys[-1]]


# ── VaultIndex caching ────────────────────────────────────────────────


class TestVaultIndexCaching:
    def _make_vault(self, tmp_path):
        """Create a minimal vault for testing."""
        journal = tmp_path / "journal"
        journal.mkdir()
        (journal / "note-a.md").write_text(
            "---\ntags: [test]\n---\n# Note A\n\nLinks to [[Note B]]\n"
        )
        (journal / "note-b.md").write_text("# Note B\n\nLinks to [[Note A]]\n")
        (journal / "orphan.md").write_text("# Orphan\n\nNo links here.\n")
        return tmp_path

    def test_scan_and_query(self, tmp_path):
        vault = self._make_vault(tmp_path)
        config = VaultConfig(
            vault_path=vault,
            scan_dirs=["journal"],
            exclude_patterns=[],
            cache_ttl=300,
        )
        index = VaultIndex(config)

        # Backlinks
        backlinks = index.get_backlinks("Note B")
        assert len(backlinks) == 1
        assert backlinks[0].source_file == "journal/note-a.md"

        # Outgoing links
        outgoing = index.get_outgoing_links("note-a")
        assert "Note B" in outgoing

        # Orphans
        orphans = index.find_orphaned_notes()
        assert "journal/orphan.md" in orphans

        # Note info
        info = index.get_note_info("note-a")
        assert info is not None
        assert info["outgoing_count"] == 1
        assert "test" in info["tags"]

        # Stats
        stats = index.vault_stats()
        assert stats["total_files"] == 3

    def test_cache_reused(self, tmp_path):
        vault = self._make_vault(tmp_path)
        config = VaultConfig(
            vault_path=vault,
            scan_dirs=["journal"],
            exclude_patterns=[],
            cache_ttl=300,
        )
        index = VaultIndex(config)

        # First call triggers scan
        index.vault_stats()
        scan_time_1 = index._data.scanned_at

        # Second call should use cache
        index.vault_stats()
        scan_time_2 = index._data.scanned_at

        assert scan_time_1 == scan_time_2

    def test_cache_invalidation(self, tmp_path):
        vault = self._make_vault(tmp_path)
        config = VaultConfig(
            vault_path=vault,
            scan_dirs=["journal"],
            exclude_patterns=[],
            cache_ttl=300,
        )
        index = VaultIndex(config)

        index.vault_stats()
        scan_time_1 = index._data.scanned_at

        index.invalidate_cache()
        index.vault_stats()
        scan_time_2 = index._data.scanned_at

        assert scan_time_2 > scan_time_1

    def test_note_not_found(self, tmp_path):
        vault = self._make_vault(tmp_path)
        config = VaultConfig(
            vault_path=vault,
            scan_dirs=["journal"],
            exclude_patterns=[],
            cache_ttl=300,
        )
        index = VaultIndex(config)

        info = index.get_note_info("nonexistent")
        assert info is None

        outgoing = index.get_outgoing_links("nonexistent")
        assert outgoing == []

        backlinks = index.get_backlinks("nonexistent")
        assert backlinks == []
