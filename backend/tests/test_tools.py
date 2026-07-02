"""Tests for the file tools. All run against the `sandbox` fixture (conftest.py)."""
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
