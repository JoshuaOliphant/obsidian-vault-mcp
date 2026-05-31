# ABOUTME: FastMCP server exposing Obsidian vault graph data as queryable tools.
# ABOUTME: Provides backlinks, outgoing links, broken links, orphans, note info, and vault stats.

from __future__ import annotations

from dataclasses import dataclass, field

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from obsidian_vault_mcp import __version__
from obsidian_vault_mcp.config import VaultConfig
from obsidian_vault_mcp.vault_index import BacklinkEntry, BrokenLinkEntry, VaultIndex

SERVER_INSTRUCTIONS = """You are a vault analysis assistant for an Obsidian knowledge base.
You can query the vault's link graph to find backlinks, broken links, orphaned notes, and more.

Available tools:
- get_backlinks: Find what links TO a given note
- get_outgoing_links: Find what a note links TO
- find_broken_links: Find wiki-links pointing to non-existent files
- find_orphaned_notes: Find files nobody links to
- get_note_info: Get metadata for a specific note
- vault_stats: Get overall vault health numbers
- refresh_index: Force a rescan of the vault (use after editing notes on disk)

The vault is scanned once and cached; query results may be up to OBSIDIAN_CACHE_TTL
seconds stale. Call refresh_index after the user edits notes to see changes immediately."""

mcp = FastMCP("obsidian-vault", instructions=SERVER_INSTRUCTIONS, version=__version__)

# Annotations shared by the read-only query tools: they only read the vault,
# repeated calls return the same result, and they never touch external systems.
_READONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)


# ── structured result types (drive output schemas for MCP clients) ─────


@dataclass
class NoteInfo:
    """Metadata for a single note."""

    relative_path: str
    outgoing_links: list[str]
    outgoing_count: int
    incoming_count: int
    tags: list[str]
    word_count: int
    confidence_markers: list[str] = field(default_factory=list)


@dataclass
class VaultStats:
    """Overall vault health summary."""

    total_files: int
    orphaned_notes: int
    deadend_notes: int
    broken_links: int
    unique_tags: int
    backlink_targets: int


@dataclass
class RefreshResult:
    """Outcome of a forced vault rescan."""

    refreshed: bool
    total_files: int


# Lazy-initialized on first tool call
_index: VaultIndex | None = None


def _get_index() -> VaultIndex:
    """Get or create the VaultIndex singleton."""
    global _index
    if _index is None:
        config = VaultConfig.from_env()
        _index = VaultIndex(config)
    return _index


@mcp.tool(annotations=_READONLY)
def get_backlinks(note_name: str) -> list[BacklinkEntry]:
    """Find all notes that link to a given note.

    Args:
        note_name: The note name or stem to search for (e.g., "Queen of Cups",
                   "weekly-plan", or "areas/career/README").

    Returns:
        List of backlinks, each with source_file, context_line, and line_number.
    """
    return _get_index().get_backlinks(note_name)


@mcp.tool(annotations=_READONLY)
def get_outgoing_links(note_name: str) -> list[str]:
    """Find all notes that a given note links to.

    Args:
        note_name: The note name, stem, or relative path (e.g., "2026-02-28",
                   "journal/2026/02-february/week-08/2026-02-28.md").

    Returns:
        List of link target names as they appear in [[wiki-links]].
    """
    return _get_index().get_outgoing_links(note_name)


@mcp.tool(annotations=_READONLY)
def find_broken_links() -> list[BrokenLinkEntry]:
    """Find all wiki-links pointing to non-existent files in the vault.

    Returns:
        List of broken links, each with source_file, broken_target, and line_number.
    """
    return _get_index().find_broken_links()


@mcp.tool(annotations=_READONLY)
def find_orphaned_notes() -> list[str]:
    """Find files with no inbound links (excluding README and index files).

    Returns:
        List of relative file paths for notes that no other note links to.
    """
    return _get_index().find_orphaned_notes()


@mcp.tool(annotations=_READONLY)
def get_note_info(note_name: str) -> NoteInfo:
    """Get metadata for a specific note.

    Args:
        note_name: The note name, stem, or relative path.

    Returns:
        Metadata with relative_path, outgoing_links, outgoing_count, incoming_count,
        tags, word_count, and confidence_markers.

    Raises:
        ToolError: If no note matching note_name exists in the vault.
    """
    info = _get_index().get_note_info(note_name)
    if info is None:
        raise ToolError(f"Note '{note_name}' not found in vault")
    return NoteInfo(**info)


@mcp.tool(annotations=_READONLY)
def vault_stats() -> VaultStats:
    """Get overall vault health summary.

    Returns:
        Counts for total_files, orphaned_notes, deadend_notes, broken_links,
        unique_tags, and backlink_targets.
    """
    return VaultStats(**_get_index().vault_stats())


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
def refresh_index() -> RefreshResult:
    """Force a rescan of the vault, discarding the cached index.

    Use this after notes have been created, edited, or deleted on disk so that
    subsequent queries reflect the current state without waiting for the cache
    to expire.

    Returns:
        RefreshResult with refreshed=True and the new total_files count.
    """
    index = _get_index()
    index.invalidate_cache()
    return RefreshResult(refreshed=True, total_files=index.file_count())


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
