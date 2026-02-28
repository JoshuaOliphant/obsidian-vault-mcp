# ABOUTME: Core vault parsing and graph computation logic.
# ABOUTME: Extracts wiki-links, tags, backlinks, orphans, broken links from an Obsidian vault.

from __future__ import annotations

import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from obsidian_vault_mcp.config import VaultConfig

# Wiki-link pattern: [[Target]] or [[Target|Display Text]]
WIKI_LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")

# Inline tag pattern: #word at word boundary, but NOT heading lines
INLINE_TAG_RE = re.compile(r"(?<!\w)#([a-zA-Z][\w-]*)\b")

# Confidence marker patterns
CONFIDENCE_MARKERS = ["[solid]", "[evolving]", "[hypothesis]", "[questioning]"]


@dataclass
class FileData:
    """Parsed data for a single markdown file."""

    relative_path: str
    outgoing_links: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    word_count: int = 0
    confidence_markers: list[str] = field(default_factory=list)


@dataclass
class BacklinkEntry:
    """A single backlink: which file links to a target and the line containing the link."""

    source_file: str
    context_line: str
    line_number: int


@dataclass
class BrokenLinkEntry:
    """A wiki-link pointing to a file that doesn't exist in the vault."""

    source_file: str
    broken_target: str
    line_number: int


@dataclass
class VaultData:
    """Complete parsed vault state, produced by a full scan."""

    files: dict[str, FileData]
    backlinks: dict[str, list[BacklinkEntry]]
    all_file_stems: set[str]
    scanned_at: float


class VaultIndex:
    """Cached, queryable index of an Obsidian vault's graph data."""

    def __init__(self, config: VaultConfig) -> None:
        self._config = config
        self._data: Optional[VaultData] = None

    def _is_cache_valid(self) -> bool:
        if self._data is None:
            return False
        return (time.time() - self._data.scanned_at) < self._config.cache_ttl

    def _ensure_loaded(self) -> VaultData:
        if not self._is_cache_valid():
            self._data = self._scan()
        return self._data  # type: ignore[return-value]

    def invalidate_cache(self) -> None:
        """Force a rescan on the next query."""
        self._data = None

    # ── scanning ──────────────────────────────────────────────────────

    def _scan(self) -> VaultData:
        """Full vault scan: collect files, parse, build graph structures."""
        files = collect_files(
            self._config.vault_path,
            self._config.scan_paths,
            self._config.exclude_patterns,
        )

        files_dict: dict[str, FileData] = {}
        all_file_stems: set[str] = set()

        for path in files:
            fdata = parse_file(path, self._config.vault_path)
            files_dict[fdata.relative_path] = fdata
            stem = Path(fdata.relative_path).stem
            all_file_stems.add(stem)

        backlinks = build_backlinks(files_dict, self._config.vault_path)

        return VaultData(
            files=files_dict,
            backlinks=backlinks,
            all_file_stems=all_file_stems,
            scanned_at=time.time(),
        )

    # ── public query methods ──────────────────────────────────────────

    def get_backlinks(self, note_name: str) -> list[BacklinkEntry]:
        """Find all notes that link to a given note name (stem or path)."""
        data = self._ensure_loaded()
        # Try exact match first, then stem-only match
        if note_name in data.backlinks:
            return data.backlinks[note_name]
        # Try without path prefix (just the note name)
        stem = note_name.rsplit("/", 1)[-1] if "/" in note_name else note_name
        return data.backlinks.get(stem, [])

    def get_outgoing_links(self, note_name: str) -> list[str]:
        """Find all notes a given note links to."""
        data = self._ensure_loaded()
        fdata = self._find_file(data, note_name)
        if fdata is None:
            return []
        return fdata.outgoing_links

    def find_broken_links(self) -> list[BrokenLinkEntry]:
        """Find all wiki-links pointing to non-existent files."""
        data = self._ensure_loaded()
        return find_unresolved_with_locations(
            data.files, data.all_file_stems, self._config.vault_path
        )

    def find_orphaned_notes(self) -> list[str]:
        """Find files with no inbound links (excluding README/index files)."""
        data = self._ensure_loaded()
        return find_orphans(data.files, data.backlinks)

    def get_note_info(self, note_name: str) -> Optional[dict]:
        """Get metadata for a single note: tags, word count, link counts."""
        data = self._ensure_loaded()
        fdata = self._find_file(data, note_name)
        if fdata is None:
            return None

        stem = Path(fdata.relative_path).stem
        incoming = data.backlinks.get(stem, [])

        return {
            "relative_path": fdata.relative_path,
            "outgoing_links": fdata.outgoing_links,
            "outgoing_count": len(fdata.outgoing_links),
            "incoming_count": len(incoming),
            "tags": fdata.tags,
            "word_count": fdata.word_count,
            "confidence_markers": fdata.confidence_markers,
        }

    def vault_stats(self) -> dict:
        """Overall vault health summary."""
        data = self._ensure_loaded()
        orphans = find_orphans(data.files, data.backlinks)
        deadends = find_deadends(data.files)
        broken = find_unresolved_with_locations(
            data.files, data.all_file_stems, self._config.vault_path
        )
        tag_counts = compute_tag_counts(data.files)

        return {
            "total_files": len(data.files),
            "orphaned_notes": len(orphans),
            "deadend_notes": len(deadends),
            "broken_links": len(broken),
            "unique_tags": len(tag_counts),
            "backlink_targets": len(data.backlinks),
        }

    # ── internal helpers ──────────────────────────────────────────────

    def _find_file(self, data: VaultData, note_name: str) -> Optional[FileData]:
        """Find a FileData by relative path or stem match."""
        # Try exact relative path (with or without .md)
        if note_name in data.files:
            return data.files[note_name]
        if note_name + ".md" in data.files:
            return data.files[note_name + ".md"]

        # Try stem match (last component without extension)
        target_stem = note_name.rsplit("/", 1)[-1] if "/" in note_name else note_name
        for rel_path, fdata in data.files.items():
            if Path(rel_path).stem == target_stem:
                return fdata
        return None


# ── pure functions (ported from vault-index.py) ───────────────────────


def collect_files(
    vault_path: Path, scan_dirs: list[Path], excludes: list[str]
) -> list[Path]:
    """Glob all .md files from scan dirs, apply exclusions."""
    files: list[Path] = []
    for scan_dir in scan_dirs:
        if not scan_dir.is_dir():
            continue
        for md_file in sorted(scan_dir.rglob("*.md")):
            path_str = str(md_file)
            if any(excl in path_str for excl in excludes):
                continue
            files.append(md_file)
    return files


def extract_frontmatter(content: str) -> tuple[str, str]:
    """Split content into frontmatter and body.

    Returns (frontmatter_text, body_text). If no frontmatter, returns ("", content).
    """
    if not content.startswith("---"):
        return "", content

    close_idx = content.find("\n---", 3)
    if close_idx == -1:
        return "", content

    frontmatter = content[3:close_idx]
    body = content[close_idx + 4:]
    return frontmatter, body


def parse_frontmatter_tags(frontmatter: str) -> list[str]:
    """Extract tags from YAML frontmatter text.

    Handles both formats:
      tags: [tag1, tag2, tag3]
      tags:
        - tag1
        - tag2
    """
    tags: list[str] = []

    lines = frontmatter.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()

        # Inline format: tags: [tag1, tag2]
        match = re.match(r"^tags:\s*\[([^\]]*)\]", stripped)
        if match:
            raw = match.group(1)
            for tag in raw.split(","):
                tag = tag.strip().strip("'\"")
                if tag:
                    tags.append(tag)
            return tags

        # List format: tags: followed by - items on subsequent lines
        if re.match(r"^tags:\s*$", stripped):
            for j in range(i + 1, len(lines)):
                list_line = lines[j]
                list_match = re.match(r"^\s+-\s+(.+)$", list_line)
                if list_match:
                    tag = list_match.group(1).strip().strip("'\"")
                    if tag:
                        tags.append(tag)
                elif list_line.strip() == "":
                    continue
                else:
                    break
            return tags

    return tags


def extract_inline_tags(body: str) -> list[str]:
    """Extract inline #tag patterns from body text, skipping headings and code blocks."""
    tags: set[str] = set()
    in_code_block = False

    for line in body.split("\n"):
        stripped = line.strip()

        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue

        if in_code_block:
            continue

        if re.match(r"^#+\s", stripped):
            continue

        for match in INLINE_TAG_RE.finditer(line):
            tag = match.group(1)
            prefix = line[: match.start()]
            if prefix.endswith(("http://", "https://", "/", "=")):
                continue
            tags.add(tag)

    return sorted(tags)


def parse_file(path: Path, vault_path: Path) -> FileData:
    """For a single .md file, extract links, tags, word count, and confidence markers."""
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return FileData(relative_path=str(path.relative_to(vault_path)))

    rel_path = str(path.relative_to(vault_path))

    # Strip fenced code blocks and inline code before extracting wiki-links
    content_no_code = re.sub(r"```.*?```", "", content, flags=re.DOTALL)
    content_no_code = re.sub(r"`[^`]+`", "", content_no_code)

    outgoing_links = sorted(set(WIKI_LINK_RE.findall(content_no_code)))

    frontmatter_text, body = extract_frontmatter(content)
    fm_tags = parse_frontmatter_tags(frontmatter_text)
    inline_tags = extract_inline_tags(body)

    # Merge and deduplicate, preserving order (frontmatter first)
    seen: set[str] = set()
    all_tags: list[str] = []
    for tag in fm_tags + inline_tags:
        lower_tag = tag.lower()
        if lower_tag not in seen:
            seen.add(lower_tag)
            all_tags.append(tag)

    word_count = len(content.split())

    content_lower = content.lower()
    markers = [m for m in CONFIDENCE_MARKERS if m in content_lower]

    return FileData(
        relative_path=rel_path,
        outgoing_links=outgoing_links,
        tags=all_tags,
        word_count=word_count,
        confidence_markers=markers,
    )


def build_backlinks(
    files: dict[str, FileData], vault_path: Path
) -> dict[str, list[BacklinkEntry]]:
    """Invert outgoing_links to build a backlink map with context lines."""
    backlinks: dict[str, list[BacklinkEntry]] = defaultdict(list)

    for rel_path, fdata in files.items():
        if not fdata.outgoing_links:
            continue

        # Read the file to get context lines
        full_path = vault_path / rel_path
        try:
            lines = full_path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            # Fall back to no context if file can't be read
            for link_target in fdata.outgoing_links:
                backlinks[link_target].append(
                    BacklinkEntry(
                        source_file=rel_path, context_line="", line_number=0
                    )
                )
            continue

        # Build a map of link_target -> first line containing it
        link_locations: dict[str, tuple[str, int]] = {}
        for line_num, line in enumerate(lines, start=1):
            for link_target in fdata.outgoing_links:
                if link_target in link_locations:
                    continue
                # Check if this line contains [[link_target]] or [[link_target|...]]
                if f"[[{link_target}]]" in line or f"[[{link_target}|" in line:
                    link_locations[link_target] = (line.strip(), line_num)

        for link_target in fdata.outgoing_links:
            context_line, line_num = link_locations.get(link_target, ("", 0))
            backlinks[link_target].append(
                BacklinkEntry(
                    source_file=rel_path,
                    context_line=context_line,
                    line_number=line_num,
                )
            )

    return dict(backlinks)


def find_orphans(
    files: dict[str, FileData], backlinks: dict[str, list[BacklinkEntry]]
) -> list[str]:
    """Files with zero incoming links (excluding README/index files)."""
    linked_stems: set[str] = set()
    for target, sources in backlinks.items():
        if sources:
            linked_stems.add(target)
            if "/" in target:
                linked_stems.add(target.rsplit("/", 1)[-1])

    orphans: list[str] = []
    for rel_path in files:
        stem = Path(rel_path).stem
        if stem.lower() in ("readme", "index"):
            continue
        if stem not in linked_stems:
            orphans.append(rel_path)

    return sorted(orphans)


def find_deadends(files: dict[str, FileData]) -> list[str]:
    """Files with zero outgoing wiki-links."""
    return sorted(
        rel_path for rel_path, fdata in files.items() if not fdata.outgoing_links
    )


def find_unresolved_with_locations(
    files: dict[str, FileData],
    all_file_stems: set[str],
    vault_path: Path,
) -> list[BrokenLinkEntry]:
    """Link targets that don't correspond to any existing file, with source locations."""
    # Collect all unique unresolved targets
    unresolved_targets: set[str] = set()
    for fdata in files.values():
        for link in fdata.outgoing_links:
            target_stem = link.rsplit("/", 1)[-1] if "/" in link else link
            if target_stem not in all_file_stems:
                unresolved_targets.add(link)

    if not unresolved_targets:
        return []

    # Find locations of each broken link
    broken: list[BrokenLinkEntry] = []
    for rel_path, fdata in files.items():
        file_broken = [l for l in fdata.outgoing_links if l in unresolved_targets]
        if not file_broken:
            continue

        full_path = vault_path / rel_path
        try:
            lines = full_path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            for target in file_broken:
                broken.append(
                    BrokenLinkEntry(
                        source_file=rel_path, broken_target=target, line_number=0
                    )
                )
            continue

        for target in file_broken:
            found = False
            for line_num, line in enumerate(lines, start=1):
                if f"[[{target}]]" in line or f"[[{target}|" in line:
                    broken.append(
                        BrokenLinkEntry(
                            source_file=rel_path,
                            broken_target=target,
                            line_number=line_num,
                        )
                    )
                    found = True
                    break
            if not found:
                broken.append(
                    BrokenLinkEntry(
                        source_file=rel_path, broken_target=target, line_number=0
                    )
                )

    return sorted(broken, key=lambda b: (b.source_file, b.line_number))


def compute_tag_counts(files: dict[str, FileData]) -> dict[str, int]:
    """Aggregate tag counts across all files, sorted descending."""
    counts: dict[str, int] = defaultdict(int)
    for fdata in files.values():
        for tag in fdata.tags:
            counts[tag] += 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))
