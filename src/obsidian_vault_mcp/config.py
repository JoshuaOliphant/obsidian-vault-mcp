# ABOUTME: Environment-based configuration for the Obsidian Vault MCP server.
# ABOUTME: Reads vault path, scan directories, exclusion patterns, and cache TTL from env vars.

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_SCAN_DIRS = [
    "journal",
    "areas",
    "projects",
    "resources",
    "inbox",
    "knowledge",
]

DEFAULT_EXCLUDE_PATTERNS = [
    ".claude/",
    ".obsidian/",
    "node_modules/",
    "worktrees/",
    "__pycache__/",
]

DEFAULT_CACHE_TTL = 300  # seconds


@dataclass(frozen=True)
class VaultConfig:
    """Configuration for vault scanning and caching."""

    vault_path: Path
    scan_dirs: list[str] = field(default_factory=lambda: list(DEFAULT_SCAN_DIRS))
    exclude_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDE_PATTERNS))
    cache_ttl: int = DEFAULT_CACHE_TTL

    @classmethod
    def from_env(cls) -> VaultConfig:
        """Build config from environment variables.

        Env vars:
            OBSIDIAN_VAULT_PATH: Required. Absolute path to the vault root.
            OBSIDIAN_SCAN_DIRS: Optional. Comma-separated directory names to scan.
            OBSIDIAN_EXCLUDE_PATTERNS: Optional. Comma-separated path fragments to exclude.
            OBSIDIAN_CACHE_TTL: Optional. Cache time-to-live in seconds (default 300).
        """
        vault_path_str = os.environ.get("OBSIDIAN_VAULT_PATH")
        if not vault_path_str:
            raise ValueError(
                "OBSIDIAN_VAULT_PATH environment variable is required. "
                "Set it to the absolute path of your Obsidian vault."
            )
        vault_path = Path(vault_path_str)

        scan_dirs_str = os.environ.get("OBSIDIAN_SCAN_DIRS")
        scan_dirs = (
            [d.strip() for d in scan_dirs_str.split(",") if d.strip()]
            if scan_dirs_str
            else list(DEFAULT_SCAN_DIRS)
        )

        exclude_str = os.environ.get("OBSIDIAN_EXCLUDE_PATTERNS")
        exclude_patterns = (
            [p.strip() for p in exclude_str.split(",") if p.strip()]
            if exclude_str
            else list(DEFAULT_EXCLUDE_PATTERNS)
        )

        cache_ttl_str = os.environ.get("OBSIDIAN_CACHE_TTL")
        cache_ttl = int(cache_ttl_str) if cache_ttl_str else DEFAULT_CACHE_TTL

        return cls(
            vault_path=vault_path,
            scan_dirs=scan_dirs,
            exclude_patterns=exclude_patterns,
            cache_ttl=cache_ttl,
        )

    @property
    def scan_paths(self) -> list[Path]:
        """Resolve scan directory names to full paths under vault_path."""
        return [self.vault_path / d for d in self.scan_dirs]
