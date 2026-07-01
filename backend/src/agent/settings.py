"""App settings + app-data directory. Backend-owned; the UI edits via the bridge."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


def app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    d = Path(base) / "ai-desktop-agent"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _default_roots() -> list[str]:
    home = Path.home()
    return [str(home / "Downloads"), str(home / "Documents")]


@dataclass
class Settings:
    allowed_roots: list[str] = field(default_factory=_default_roots)
    model: str = "qwen3.5:2b"
    dry_run: bool = False


def _settings_path() -> Path:
    return app_data_dir() / "settings.json"


def load_settings() -> Settings:
    p = _settings_path()
    if not p.exists():
        return Settings()
    data = json.loads(p.read_text(encoding="utf-8"))
    return Settings(
        allowed_roots=data.get("allowed_roots", _default_roots()),
        model=data.get("model", "qwen3.5:2b"),
        dry_run=data.get("dry_run", False),
    )


def save_settings(s: Settings) -> None:
    _settings_path().write_text(json.dumps(asdict(s), indent=2), encoding="utf-8")
