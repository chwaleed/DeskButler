import pytest
from pathlib import Path
from agent.safety import resolve_and_check, PathNotAllowed


def test_path_inside_root_is_allowed(tmp_path):
    root = tmp_path / "Downloads"
    root.mkdir()
    target = root / "file.txt"
    target.write_text("x")
    out = resolve_and_check(str(target), roots=[str(root)])
    assert out == target.resolve()


def test_path_outside_root_is_rejected(tmp_path):
    root = tmp_path / "Downloads"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("x")
    with pytest.raises(PathNotAllowed):
        resolve_and_check(str(outside), roots=[str(root)])


def test_dotdot_traversal_is_rejected(tmp_path):
    root = tmp_path / "Downloads"
    root.mkdir()
    escape = str(root / ".." / "secret.txt")
    with pytest.raises(PathNotAllowed):
        resolve_and_check(escape, roots=[str(root)])


def test_case_insensitive_match_is_allowed(tmp_path):
    root = tmp_path / "Downloads"
    root.mkdir()
    target = root / "file.txt"
    target.write_text("x")
    # Windows path compare is case-insensitive; upper-cased root must still match.
    out = resolve_and_check(str(target), roots=[str(root).upper()])
    assert out == target.resolve()


def test_unc_path_is_rejected(tmp_path):
    root = tmp_path / "Downloads"
    root.mkdir()
    with pytest.raises(PathNotAllowed):
        resolve_and_check(r"\\server\share\file.txt", roots=[str(root)])


def test_device_prefix_is_rejected(tmp_path):
    root = tmp_path / "Downloads"
    root.mkdir()
    with pytest.raises(PathNotAllowed):
        resolve_and_check(r"\\?\C:\Windows\system32\config", roots=[str(root)])
