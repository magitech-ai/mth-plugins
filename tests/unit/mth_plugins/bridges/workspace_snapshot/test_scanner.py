"""Unit tests for worktree scanning, gitignore matching, and bound enforcement."""

from pathlib import Path
from unittest.mock import patch

from mth_plugins.bridges.workspace_snapshot.scanner import (
    GitignoreRule,
    is_ignored,
    parse_gitignore_file,
    scan_worktree,
    translate_gitignore_pattern,
)


def test_translate_gitignore_pattern() -> None:
    # 1. Double star patterns
    assert ".*" in translate_gitignore_pattern("**/")
    assert ".*" in translate_gitignore_pattern("abc/**")
    assert "[^/]*" in translate_gitignore_pattern("abc/**xyz")

    # 2. Single star and question mark
    assert "[^/]*" in translate_gitignore_pattern("*.py")
    assert "[^/]" in translate_gitignore_pattern("file?.txt")

    # 3. Character classes
    assert "[abc]" in translate_gitignore_pattern("[abc]")
    assert "[^abc]" in translate_gitignore_pattern("[!abc]")
    assert "[]abc]" in translate_gitignore_pattern("[]abc]")
    assert translate_gitignore_pattern("[unterminated") == r"\[unterminated"

    # 4. Escaping special regex characters
    assert r"\." in translate_gitignore_pattern("file.txt")
    assert r"\+" in translate_gitignore_pattern("a+b")


def test_gitignore_rule_parsing_and_matching() -> None:
    # 1. Blank or comment
    assert GitignoreRule.parse("") is None
    assert GitignoreRule.parse("   # comment") is None

    # 2. Negation rule
    r_neg = GitignoreRule.parse("!important.txt")
    assert r_neg is not None
    assert r_neg.is_negation is True
    assert r_neg.matches("important.txt", is_dir=False)

    # 3. Directory only rule
    r_dir = GitignoreRule.parse("build/")
    assert r_dir is not None
    assert r_dir.dir_only is True
    assert r_dir.matches("build", is_dir=True)
    assert not r_dir.matches("build", is_dir=False)

    # 4. Root anchored rule
    r_root = GitignoreRule.parse("/config.json")
    assert r_root is not None
    assert r_root.matches("config.json", is_dir=False)
    assert not r_root.matches("sub/config.json", is_dir=False)

    # 5. Relative subpath rule
    r_sub = GitignoreRule.parse("src/gen/*.py")
    assert r_sub is not None
    assert r_sub.matches("src/gen/app.py", is_dir=False)
    assert not r_sub.matches("other/app.py", is_dir=False)


def test_parse_gitignore_file(tmp_path: Path) -> None:
    # Missing file returns []
    assert parse_gitignore_file(tmp_path / "missing.ignore") == []

    # Valid file
    gi_path = tmp_path / ".gitignore"
    gi_path.write_text("*.log\n# comment\nnode_modules/\n!keep.log\n", encoding="utf-8")
    rules = parse_gitignore_file(gi_path)
    assert len(rules) == 3

    # Reverse precedence in is_ignored
    assert is_ignored("app.log", is_dir=False, rules=rules) is True
    assert is_ignored("keep.log", is_dir=False, rules=rules) is False
    assert is_ignored("node_modules", is_dir=True, rules=rules) is True
    assert is_ignored("app.py", is_dir=False, rules=rules) is False

    # OSError on open
    with patch.object(Path, "open", side_effect=OSError("permission denied")):
        assert parse_gitignore_file(gi_path) == []


def test_scan_worktree_bounds_and_exclusions(tmp_path: Path) -> None:
    # 1. Non-existent directory
    assert scan_worktree(tmp_path / "nonexistent") == (0, 0, False)

    # 2. Normal worktree
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / ".git").mkdir()
    (ws / ".git" / "HEAD").write_text("ref", encoding="utf-8")
    (ws / ".agents").mkdir()
    (ws / ".agents" / "secrets.txt").write_text("secret", encoding="utf-8")

    (ws / "file1.txt").write_text("hello", encoding="utf-8")
    sub = ws / "sub"
    sub.mkdir()
    (sub / "file2.txt").write_text("world!", encoding="utf-8")
    (ws / ".gitignore").write_text("*.bak\n", encoding="utf-8")
    (ws / "ignored.bak").write_text("ignored data", encoding="utf-8")

    count, bytes_total, over = scan_worktree(ws)
    assert count == 3  # file1.txt, file2.txt, .gitignore (.git, .agents, .bak ignored)
    assert bytes_total > 0
    assert over is False

    # 3. Exceed max_files bound
    _, _, over_files = scan_worktree(ws, max_files=1)
    assert over_files is True

    # 4. Exceed max_bytes bound
    _, _, over_bytes = scan_worktree(ws, max_bytes=2)
    assert over_bytes is True

    # 5. Handle unreadable directory gracefully
    with patch("os.scandir", side_effect=OSError("dir unreadable")):
        c, b, o = scan_worktree(ws)
        assert c == 0 and b == 0 and o is False

    # 6. Handle stat failure gracefully on individual file
    with patch("os.DirEntry.stat", side_effect=OSError("stat error")):
        c, b, o = scan_worktree(ws)
        assert c == 3 and b == 0 and o is False
