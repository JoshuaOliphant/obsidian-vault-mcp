# ABOUTME: FastMCP server exposing Obsidian vault graph data as queryable tools.
# ABOUTME: Provides backlinks, outgoing links, broken links, orphans, note info, and vault stats.

from __future__ import annotations

from fastmcp import FastMCP

from obsidian_vault_mcp.config import VaultConfig
from obsidian_vault_mcp.vault_index import VaultIndex

SERVER_INSTRUCTIONS = """You are a vault analysis assistant for an Obsidian knowledge base.
You can query the vault's link graph to find backlinks, broken links, orphaned notes, and more.

Available tools:
- get_backlinks: Find what links TO a given note
- get_outgoing_links: Find what a note links TO
- find_broken_links: Find wiki-links pointing to non-existent files
- find_orphaned_notes: Find files nobody links to
- get_note_info: Get metadata for a specific note
- vault_stats: Get overall vault health numbers"""

mcp = FastMCP("obsidian-vault", instructions=SERVER_INSTRUCTIONS)

# Lazy-initialized on first tool call
_index: VaultIndex | None = None


def _get_index() -> VaultIndex:
    """Get or create the VaultIndex singleton."""
    global _index
    if _index is None:
        config = VaultConfig.from_env()
        _index = VaultIndex(config)
    return _index


@mcp.tool
def get_backlinks(note_name: str) -> list[dict]:
    """Find all notes that link to a given note.

    Args:
        note_name: The note name or stem to search for (e.g., "Queen of Cups",
                   "weekly-plan", or "areas/career/README").

    Returns:
        List of backlinks, each with source_file, context_line, and line_number.
    """
    entries = _get_index().get_backlinks(note_name)
    return [
        {
            "source_file": e.source_file,
            "context_line": e.context_line,
            "line_number": e.line_number,
        }
        for e in entries
    ]


@mcp.tool
def get_outgoing_links(note_name: str) -> list[str]:
    """Find all notes that a given note links to.

    Args:
        note_name: The note name, stem, or relative path (e.g., "2026-02-28",
                   "journal/2026/02-february/week-08/2026-02-28.md").

    Returns:
        List of link target names as they appear in [[wiki-links]].
    """
    return _get_index().get_outgoing_links(note_name)


@mcp.tool
def find_broken_links() -> list[dict]:
    """Find all wiki-links pointing to non-existent files in the vault.

    Returns:
        List of broken links, each with source_file, broken_target, and line_number.
    """
    entries = _get_index().find_broken_links()
    return [
        {
            "source_file": e.source_file,
            "broken_target": e.broken_target,
            "line_number": e.line_number,
        }
        for e in entries
    ]


@mcp.tool
def find_orphaned_notes() -> list[str]:
    """Find files with no inbound links (excluding README and index files).

    Returns:
        List of relative file paths for notes that no other note links to.
    """
    return _get_index().find_orphaned_notes()


@mcp.tool
def get_note_info(note_name: str) -> dict:
    """Get metadata for a specific note.

    Args:
        note_name: The note name, stem, or relative path.

    Returns:
        Dict with relative_path, outgoing_links, outgoing_count, incoming_count,
        tags, word_count, and confidence_markers. Returns an error dict if not found.
    """
    info = _get_index().get_note_info(note_name)
    if info is None:
        return {"error": f"Note '{note_name}' not found in vault"}
    return info


@mcp.tool
def vault_stats() -> dict:
    """Get overall vault health summary.

    Returns:
        Dict with total_files, orphaned_notes, deadend_notes, broken_links,
        unique_tags, and backlink_targets counts.
    """
    return _get_index().vault_stats()


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
