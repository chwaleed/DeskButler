import pytest


class FakeSettings:
    def __init__(self, roots):
        self.allowed_roots = roots
        self.model = "test"
        self.dry_run = False


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """A temp allowed root with settings + audit patched so tools run isolated.

    Returns (root, settings). Flip settings.dry_run = True inside a test to
    exercise dry-run behavior.
    """
    root = tmp_path / "Downloads"
    root.mkdir()
    settings = FakeSettings([str(root)])
    monkeypatch.setattr("agent.safety.load_settings", lambda: settings)
    monkeypatch.setattr("agent.safety.app_data_dir", lambda: tmp_path)
    return root, settings
