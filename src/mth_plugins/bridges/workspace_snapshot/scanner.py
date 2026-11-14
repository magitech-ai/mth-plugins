"""Worktree scanning with gitignore filtering and file/byte safety bounds."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

MAX_CAPTURE_FILES = 50_000
MAX_CAPTURE_BYTES = 1024 * 1024 * 1024  # 1 GiB
EXCLUDED_DIR_NAMES = frozenset({".git", ".agents"})


def _translate_bracket(pattern: str, i: int, n: int) -> tuple[str, int]:
    """Translates a bracket character class expression from wildmatch."""
    j = i + 1
    if j < n and pattern[j] in "!^":
        j += 1
    if j < n and pattern[j] == "]":
        j += 1
    while j < n and pattern[j] != "]":
        j += 1
    if j >= n:
        return r"\[", i + 1
    stuff = pattern[i + 1 : j]
    if stuff.startswith("!"):
        stuff = "^" + stuff[1:]
    stuff = stuff.replace("\\", "\\\\")
    return f"[{stuff}]", j + 1


def translate_gitignore_pattern(pattern: str) -> str:
    """Translates a gitignore wildmatch pattern to a regex body."""
    out: list[str] = []
    i = 0
    n = len(pattern)
    while i < n:
        ch = pattern[i]
        if ch == "*":
            if pattern[i : i + 2] == "**":
                if i + 2 >= n:
                    out.append(".*")
                    i += 2
                    continue
                if pattern[i + 2] == "/":
                    out.append("(?:.*/)?")
                    i += 3
                    continue
                out.append("[^/]*")
                i += 2
                continue
            out.append("[^/]*")
            i += 1
            continue
        if ch == "?":
            out.append("[^/]")
            i += 1
            continue
        if ch == "[":
            piece, i = _translate_bracket(pattern, i, n)
            out.append(piece)
            continue
        if ch in r"\.+$^(){}":
            out.append("\\" + ch)
        else:
            out.append(ch)
        i += 1
    return "".join(out)


@dataclass(frozen=True)
class GitignoreRule:
    """Represents a single parsed gitignore pattern."""

    pattern: str
    regex: re.Pattern[str]
    is_negation: bool
    dir_only: bool

    @classmethod
    def parse(cls, raw: str) -> GitignoreRule | None:
        line = raw.strip()
        if not line or line.startswith("#"):
            return None

        is_negation = line.startswith("!")
        if is_negation:
            line = line[1:].strip()

        dir_only = line.endswith("/")
        if dir_only:
            line = line[:-1]

        # Leading slash anchors to root
        if line.startswith("/"):
            line = line[1:]
            regex_str = f"^{translate_gitignore_pattern(line)}$"
        elif "/" in line:
            regex_str = f"^{translate_gitignore_pattern(line)}$"
        else:
            regex_str = f"(?:^|/){translate_gitignore_pattern(line)}$"

        return cls(
            pattern=raw,
            regex=re.compile(regex_str),
            is_negation=is_negation,
            dir_only=dir_only,
        )

    def matches(self, rel_path: str, is_dir: bool) -> bool:
        if self.dir_only and not is_dir:
            return False
        return bool(self.regex.search(rel_path))


def parse_gitignore_file(path: Path) -> list[GitignoreRule]:
    """Parses rules from a .gitignore file, if it exists."""
    if not path.is_file():
        return []
    rules: list[GitignoreRule] = []
    try:
        with path.open(encoding="utf-8", errors="ignore") as f:
            for line in f:
                r = GitignoreRule.parse(line)
                if r is not None:
                    rules.append(r)
    except OSError:
        pass
    return rules


def is_ignored(rel_path: str, is_dir: bool, rules: list[GitignoreRule]) -> bool:
    """Determines whether a path is ignored by evaluating rules in reverse."""
    for rule in reversed(rules):
        if rule.matches(rel_path, is_dir):
            return not rule.is_negation
    return False


def scan_worktree(
    workspace: Path,
    git_dir: Path | None = None,
    max_files: int = MAX_CAPTURE_FILES,
    max_bytes: int = MAX_CAPTURE_BYTES,
) -> tuple[int, int, bool]:
    """Counts files and bytes under workspace, terminating early if exceeding bounds."""
    if not workspace.is_dir():
        return 0, 0, False

    file_count = 0
    byte_count = 0

    # Traversal state: dir_path, inherited_rules, rel_dir
    stack: list[tuple[Path, list[GitignoreRule], str]] = [(workspace, [], "")]

    while stack:
        curr_dir, parent_rules, rel_dir = stack.pop()
        dir_rules = list(parent_rules)
        gi_file = curr_dir / ".gitignore"
        if gi_file.is_file():
            dir_rules.extend(parse_gitignore_file(gi_file))

        try:
            with os.scandir(curr_dir) as entries:
                for entry in entries:
                    name = entry.name
                    if name in EXCLUDED_DIR_NAMES:
                        continue

                    rel_entry = f"{rel_dir}/{name}".lstrip("/")
                    is_dir = entry.is_dir(follow_symlinks=False)

                    if is_ignored(rel_entry, is_dir, dir_rules):
                        continue

                    if is_dir:
                        stack.append((Path(entry.path), dir_rules, rel_entry))
                    else:
                        file_count += 1
                        try:
                            byte_count += entry.stat().st_size
                        except OSError:
                            pass

                        if file_count > max_files or byte_count > max_bytes:
                            return file_count, byte_count, True
        except OSError:
            continue

    return file_count, byte_count, False
