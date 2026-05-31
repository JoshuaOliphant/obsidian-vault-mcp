# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-05-31

### Added
- `refresh_index` tool to force a vault rescan after notes change on disk,
  instead of waiting out the cache TTL.
- Read-only [tool annotations](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
  (`readOnlyHint`, `idempotentHint`, `openWorldHint`) on every tool so clients
  know which calls are safe and cacheable.
- Structured output: tools now return typed objects, so FastMCP emits output
  schemas and `structuredContent` for each result.
- The server now reports its own version in the MCP `initialize` handshake
  (`serverInfo.version`), wired to the package version. Previously the handshake
  reported FastMCP's version instead.
- `ty` type checking and a GitHub Actions CI workflow (ruff + ty + pytest on
  Python 3.11–3.13).

### Changed
- **Breaking:** `get_note_info` now raises a `ToolError` when a note is not
  found, instead of returning `{"error": ...}`. This aligns with the MCP
  guidance that input/validation failures be tool execution errors the model
  can self-correct from.
- Require `fastmcp >= 3.3.1` (was `>= 2.0.0`).

## [0.1.0]

### Added
- Initial release with `get_backlinks`, `get_outgoing_links`,
  `find_broken_links`, `find_orphaned_notes`, `get_note_info`, and
  `vault_stats` tools over an in-memory Obsidian vault link graph.
