import json
import pytest
from pathlib import Path
from agent.safety import resolve_and_check, resolve_allowed, PathNotAllowed, recycle_delete, audit


def test_resolve_allowed_maps_loose_name_to_root(tmp_path):
    root = tmp_path / "Downloads"
    root.mkdir()
    # A bare loose name matches the allowed root by basename (no cwd resolution).
    assert resolve_allowed("Downloads", roots=[str(root)]) == root.resolve()
    # "my downloads" and leading "root/" noise are tolerated too.
    assert resolve_allowed("my downloads", roots=[str(root)]) == root.resolve()
    (root / "a.txt").write_text("x")
    assert resolve_allowed("root/Downloads/a.txt", roots=[str(root)]) == (root / "a.txt").resolve()


def test_resolve_allowed_still_denies_real_escape(tmp_path):
    root = tmp_path / "Downloads"
    root.mkdir()
    with pytest.raises(PathNotAllowed):
        resolve_allowed(r"..\Secret", roots=[str(root)])  # relative escape above the root
    with pytest.raises(PathNotAllowed):
        resolve_allowed(r"..\..\Secret\x.txt", roots=[str(root)])  # deeper escape
    with pytest.raises(PathNotAllowed):
        resolve_allowed(r"C:\Windows\system32", roots=[str(root)])  # absolute, outside


def test_resolve_allowed_bare_name_resolves_inside_root(tmp_path):
    # The model refers to files by their bare name, meaning "inside my allowed folder".
    # That must resolve into the root, not against the backend's cwd.
    root = tmp_path / "Downloads"
    root.mkdir()
    (root / "photo.jpg").write_text("x")
    assert resolve_allowed("photo.jpg", roots=[str(root)]) == (root / "photo.jpg").resolve()
    # A file with spaces (like the real "11th Result.jpg") resolves the same way.
    (root / "11th Result.jpg").write_text("x")
    assert resolve_allowed("11th Result.jpg", roots=[str(root)]) == (root / "11th Result.jpg").resolve()


def test_resolve_allowed_relative_subpath_for_new_destination(tmp_path):
    # "images/photo.jpg" as a move destination (doesn't exist yet) resolves under the
    # root whose parent subfolder exists — the organize-into-a-subfolder case.
    root = tmp_path / "Downloads"
    root.mkdir()
    (root / "images").mkdir()
    got = resolve_allowed(r"images\photo.jpg", roots=[str(root)])
    assert got == (root / "images" / "photo.jpg").resolve()


def test_resolve_allowed_prefers_root_where_file_exists(tmp_path):
    # With several allowed roots, a bare name resolves to the root that actually has it.
    downloads = tmp_path / "Downloads"
    docs = tmp_path / "Documents"
    downloads.mkdir()
    docs.mkdir()
    (docs / "report.pdf").write_text("x")
    got = resolve_allowed("report.pdf", roots=[str(downloads), str(docs)])
    assert got == (docs / "report.pdf").resolve()


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


def test_move_file_dry_run_does_not_move(tmp_path, monkeypatch):
    from agent import tools
    root = tmp_path / "Downloads"
    root.mkdir()
    src = root / "a.txt"
    src.write_text("x")
    dst = root / "b.txt"
    monkeypatch.setattr("agent.tools.dry_run", lambda: True)
    monkeypatch.setattr(
        "agent.safety.load_settings",
        lambda: type("S", (), {"allowed_roots": [str(root)], "dry_run": True})(),
    )
    result = tools.move_file.invoke({"src": str(src), "dst": str(dst)})
    assert "dry-run" in result.lower()
    assert src.exists() and not dst.exists()


def test_needs_approval_matrix():
    from agent.safety import needs_approval
    # Name-based destructive tools always gate.
    assert needs_approval("move_file", {})
    assert needs_approval("delete_file", {})
    assert needs_approval("batch_move", {"moves": [{"src": "a", "dst": "b"}]})
    # Read-only / creating tools don't.
    assert not needs_approval("list_dir", {})
    assert not needs_approval("copy_file", {})
    # write_file gates ONLY when overwriting.
    assert not needs_approval("write_file", {"path": "a.txt", "content": "x"})
    assert not needs_approval("write_file", {"overwrite": False})
    assert needs_approval("write_file", {"overwrite": True})
    # Missing args tolerated.
    assert not needs_approval("write_file", None)


def test_system_prompt_teaches_batch_and_rename():
    from agent.prompts import system_prompt
    p = system_prompt([r"C:\Users\x\Downloads"])
    assert r"C:\Users\x\Downloads" in p
    assert "batch_move" in p
    assert "rename" in p.lower()
