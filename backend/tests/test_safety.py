import json
import pytest
from pathlib import Path
from agent.safety import resolve_and_check, PathNotAllowed, recycle_delete, audit


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


def test_recycle_delete_removes_file(tmp_path, monkeypatch):
    calls = {}
    def fake_send2trash(p):
        calls["path"] = p
    monkeypatch.setattr("agent.safety.send2trash", fake_send2trash)
    f = tmp_path / "gone.txt"
    f.write_text("x")
    recycle_delete(f)
    assert calls["path"] == str(f)


def test_audit_appends_json_line(tmp_path, monkeypatch):
    monkeypatch.setattr("agent.safety.app_data_dir", lambda: tmp_path)
    audit({"tool": "move_file", "result": "ok"})
    audit({"tool": "list_dir", "result": "ok"})
    lines = (tmp_path / "audit.log").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["tool"] == "move_file"
