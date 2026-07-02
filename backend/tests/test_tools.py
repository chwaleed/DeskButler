"""Tests for the file tools. All run against the `sandbox` fixture (conftest.py)."""
import pytest

from agent import tools


# ---- read_file ----

def test_read_file_returns_content(sandbox):
    root, _ = sandbox
    f = root / "note.txt"
    f.write_text("hello world", encoding="utf-8")
    assert tools.read_file.invoke({"path": str(f)}) == "hello world"


def test_read_file_caps_output(sandbox):
    root, _ = sandbox
    f = root / "big.txt"
    f.write_text("x" * 50_000, encoding="utf-8")
    out = tools.read_file.invoke({"path": str(f)})
    assert len(out) < 12_000
    assert "truncated" in out


def test_read_file_refuses_binary(sandbox):
    root, _ = sandbox
    f = root / "app.bin"
    f.write_bytes(b"MZ\x00\x01\x02binary")
    out = tools.read_file.invoke({"path": str(f)})
    assert "Refused" in out


def test_read_file_denies_outside_roots(sandbox):
    out = tools.read_file.invoke({"path": r"C:\Windows\win.ini"})
    assert out.startswith("Denied:")


# ---- file_info ----

def test_file_info_reports_size_and_type(sandbox):
    root, _ = sandbox
    f = root / "doc.pdf"
    f.write_bytes(b"x" * 2048)
    out = tools.file_info.invoke({"path": str(f)})
    assert "2.0 KB" in out
    assert ".pdf" in out
    assert "modified:" in out


def test_file_info_on_folder(sandbox):
    root, _ = sandbox
    out = tools.file_info.invoke({"path": str(root)})
    assert "folder" in out


# ---- create_folder ----

def test_create_folder_creates_with_parents(sandbox):
    root, _ = sandbox
    target = root / "sorted" / "images"
    out = tools.create_folder.invoke({"path": str(target)})
    assert target.is_dir()
    assert "Created" in out


def test_create_folder_noop_if_exists(sandbox):
    root, _ = sandbox
    out = tools.create_folder.invoke({"path": str(root)})
    assert "Already exists" in out


def test_create_folder_dry_run(sandbox):
    root, settings = sandbox
    settings.dry_run = True
    target = root / "newdir"
    out = tools.create_folder.invoke({"path": str(target)})
    assert "[dry-run]" in out
    assert not target.exists()


# ---- copy_file ----

def test_copy_file_copies(sandbox):
    root, _ = sandbox
    src = root / "a.txt"
    src.write_text("data")
    dst = root / "backup" / "a.txt"
    out = tools.copy_file.invoke({"src": str(src), "dst": str(dst)})
    assert dst.read_text() == "data"
    assert src.exists()  # copy, not move
    assert "Copied" in out


def test_copy_file_refuses_existing_destination(sandbox):
    root, _ = sandbox
    src = root / "a.txt"
    src.write_text("new")
    dst = root / "b.txt"
    dst.write_text("old")
    out = tools.copy_file.invoke({"src": str(src), "dst": str(dst)})
    assert "Denied" in out
    assert dst.read_text() == "old"


def test_copy_file_copies_folder(sandbox):
    root, _ = sandbox
    (root / "proj").mkdir()
    (root / "proj" / "f.txt").write_text("x")
    out = tools.copy_file.invoke({"src": str(root / "proj"), "dst": str(root / "proj2")})
    assert (root / "proj2" / "f.txt").read_text() == "x"
    assert "Copied" in out


# ---- write_file ----

def test_write_file_creates_text_file(sandbox):
    root, _ = sandbox
    target = root / "notes" / "todo.md"
    out = tools.write_file.invoke({"path": str(target), "content": "# Todo\n- buy milk"})
    assert target.read_text(encoding="utf-8") == "# Todo\n- buy milk"
    assert "Wrote" in out


def test_write_file_refuses_overwrite_without_flag(sandbox):
    root, _ = sandbox
    f = root / "keep.txt"
    f.write_text("original")
    out = tools.write_file.invoke({"path": str(f), "content": "clobbered"})
    assert "Denied" in out
    assert f.read_text() == "original"


def test_write_file_overwrites_with_flag(sandbox):
    root, _ = sandbox
    f = root / "keep.txt"
    f.write_text("original")
    out = tools.write_file.invoke({"path": str(f), "content": "new", "overwrite": True})
    assert f.read_text(encoding="utf-8") == "new"
    assert "Wrote" in out


def test_write_file_refuses_executable_extension(sandbox):
    root, _ = sandbox
    out = tools.write_file.invoke({"path": str(root / "evil.bat"), "content": "del /q *"})
    assert "Denied" in out
    assert not (root / "evil.bat").exists()


def test_write_file_dry_run(sandbox):
    root, settings = sandbox
    settings.dry_run = True
    target = root / "new.txt"
    out = tools.write_file.invoke({"path": str(target), "content": "x"})
    assert "[dry-run]" in out
    assert not target.exists()


# ---- delete_file ----

def test_delete_file_sends_to_recycle_bin(sandbox, monkeypatch):
    root, _ = sandbox
    trashed = []
    monkeypatch.setattr("agent.tools.recycle_delete", lambda p: trashed.append(str(p)))
    f = root / "old.txt"
    f.write_text("x")
    out = tools.delete_file.invoke({"path": str(f)})
    assert trashed == [str(f.resolve())]
    assert "Recycle Bin" in out


def test_delete_file_refuses_allowed_root_itself(sandbox, monkeypatch):
    root, _ = sandbox
    trashed = []
    monkeypatch.setattr("agent.tools.recycle_delete", lambda p: trashed.append(str(p)))
    out = tools.delete_file.invoke({"path": str(root)})
    assert "Denied" in out
    assert trashed == []


def test_delete_file_dry_run(sandbox, monkeypatch):
    root, settings = sandbox
    settings.dry_run = True
    trashed = []
    monkeypatch.setattr("agent.tools.recycle_delete", lambda p: trashed.append(str(p)))
    f = root / "old.txt"
    f.write_text("x")
    out = tools.delete_file.invoke({"path": str(f)})
    assert "[dry-run]" in out
    assert trashed == [] and f.exists()


def test_delete_file_missing_path(sandbox, monkeypatch):
    root, _ = sandbox
    monkeypatch.setattr("agent.tools.recycle_delete",
                        lambda p: pytest.fail("recycle_delete must not run on a missing path"))
    out = tools.delete_file.invoke({"path": str(root / "ghost.txt")})
    assert "Not found" in out


# ---- folder_stats ----

def test_folder_stats_groups_by_extension(sandbox):
    root, _ = sandbox
    (root / "a.jpg").write_bytes(b"x" * 1000)
    (root / "b.jpg").write_bytes(b"x" * 1000)
    (root / "c.pdf").write_bytes(b"x" * 5000)
    (root / "sub").mkdir()
    (root / "sub" / "d.jpg").write_bytes(b"x" * 1000)  # recursive
    out = tools.folder_stats.invoke({"path": str(root)})
    assert "4 files" in out
    assert ".jpg: 3 files" in out
    assert ".pdf: 1 files" in out


def test_folder_stats_handles_no_extension(sandbox):
    root, _ = sandbox
    (root / "README").write_bytes(b"x")
    out = tools.folder_stats.invoke({"path": str(root)})
    assert "(none): 1 files" in out


def test_folder_stats_denies_outside_roots(sandbox):
    out = tools.folder_stats.invoke({"path": r"C:\Windows"})
    assert out.startswith("Denied:")
