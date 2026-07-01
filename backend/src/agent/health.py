"""Startup readiness check for the local Ollama daemon."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from agent.settings import load_settings


def check_ollama(base_url: str = "http://localhost:11434") -> tuple[bool, str]:
    model = load_settings().model
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return False, "Ollama is not running. Start it, then reopen the app."
    names = {m.get("name", "").split(":")[0] for m in data.get("models", [])}
    tags = {m.get("name", "") for m in data.get("models", [])}
    if model in tags or model.split(":")[0] in names:
        return True, "ok"
    return False, f"Model '{model}' is not installed. Run: ollama pull {model}"
