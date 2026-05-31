# ABOUTME: Package entry point for the Obsidian Vault MCP server.
# ABOUTME: Exposes the package version plus the FastMCP server instance and main().

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("obsidian-vault-mcp")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "0.0.0+unknown"

from obsidian_vault_mcp.server import main, mcp

__all__ = ["__version__", "main", "mcp"]
