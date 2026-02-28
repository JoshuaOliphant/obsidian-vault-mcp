# Obsidian Vault MCP Server

An MCP (Model Context Protocol) server that exposes your Obsidian vault's link graph as queryable tools. Find backlinks, broken links, orphaned notes, and more — directly from Claude Code or any MCP client.

## Why?

Obsidian has great graph features in the GUI, but there's no programmatic way for AI agents to query your vault's structure. Existing MCP servers for Obsidian are either unmaintained or lack graph-aware tooling.

This server parses your vault's markdown files, builds an in-memory link graph, and exposes it through 6 focused tools.

## Tools

| Tool | Description |
|------|-------------|
| `get_backlinks` | Find all notes that link to a given note |
| `get_outgoing_links` | Find all notes a given note links to |
| `find_broken_links` | Find `[[wiki-links]]` pointing to non-existent files |
| `find_orphaned_notes` | Find files with no inbound links |
| `get_note_info` | Get metadata for a note (tags, word count, link counts) |
| `vault_stats` | Overall vault health summary |

## Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Install

```bash
git clone https://github.com/joshuaoliphant/obsidian-vault-mcp.git
cd obsidian-vault-mcp
uv sync
```

### Configure in Claude Code

Add to `~/.claude/settings.json` under `mcpServers`:

```json
{
  "obsidian-vault": {
    "command": "uv",
    "args": [
      "run", "--directory",
      "/path/to/obsidian-vault-mcp",
      "python", "-m", "obsidian_vault_mcp"
    ],
    "env": {
      "OBSIDIAN_VAULT_PATH": "/path/to/your/obsidian/vault"
    }
  }
}
```

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OBSIDIAN_VAULT_PATH` | Yes | — | Absolute path to your Obsidian vault |
| `OBSIDIAN_SCAN_DIRS` | No | `journal,areas,projects,resources,inbox,knowledge` | Comma-separated directory names to scan |
| `OBSIDIAN_EXCLUDE_PATTERNS` | No | `.claude/,.obsidian/,node_modules/,worktrees/,__pycache__/` | Comma-separated path fragments to exclude |
| `OBSIDIAN_CACHE_TTL` | No | `300` | Cache time-to-live in seconds |

## Usage Examples

Once registered, the tools are available in Claude Code:

```
> What links to my "Weekly Review" note?
# Claude calls get_backlinks("Weekly Review")

> Are there any broken links in my vault?
# Claude calls find_broken_links()

> Show me notes that nobody links to
# Claude calls find_orphaned_notes()

> How healthy is my vault?
# Claude calls vault_stats()
```

## Performance

Tested on a 1,100-file vault:
- Cold scan: ~0.4 seconds
- Cached queries: ~20ms
- Cache auto-refreshes based on `OBSIDIAN_CACHE_TTL`

## Development

```bash
# Run tests
uv run pytest tests/ -v

# Run the server directly
OBSIDIAN_VAULT_PATH=/path/to/vault uv run python -m obsidian_vault_mcp
```

## License

MIT
