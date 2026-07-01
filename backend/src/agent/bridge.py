"""pywebview Api: the JS<->Python boundary. Methods run on pywebview's own threads."""
from __future__ import annotations

import json
from dataclasses import asdict

from agent.runtime import Runtime
from agent.settings import Settings, load_settings, save_settings


class Api:
    def __init__(self):
        self._window = None
        self._runtime = Runtime(emit=self._emit)

    def set_window(self, window) -> None:
        self._window = window
        self._runtime.start()

    def _emit(self, event: dict) -> None:
        if self._window is not None:
            payload = json.dumps(event)
            self._window.evaluate_js(f"window.onAgentEvent({payload})")

    # --- exposed to JS ---
    def send_message(self, text: str) -> str:
        return self._runtime.send(text)

    def approve(self, decision: dict) -> None:
        self._runtime.resume(decision)

    def cancel(self) -> None:
        self._runtime.cancel()

    def get_settings(self) -> dict:
        return asdict(load_settings())

    def save_settings(self, data: dict) -> None:
        save_settings(Settings(**data))
