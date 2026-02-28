# ABOUTME: Package entry point for the Obsidian Vault MCP server.
# ABOUTME: Exports the FastMCP server instance and main() entry point.

from obsidian_vault_mcp.server import main, mcp

__all__ = ["main", "mcp"]
