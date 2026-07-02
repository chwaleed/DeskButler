"""Entry point: readiness check, create the window, start the runtime."""
from __future__ import annotations

import json
from pathlib import Path

import webview

from agent.bridge import Api
from agent.health import check_ollama
from agent.logs import get_logger, setup_logging

log = get_logger("main")

_PLACEHOLDER = "<html><body style='font-family:sans-serif;padding:2rem'>Backend running. Build the frontend to see the UI.</body></html>"


def _frontend_entry() -> str:
    dist = Path(__file__).resolve().parents[3] / "frontend" / "dist" / "index.html"
    return str(dist) if dist.exists() else _PLACEHOLDER


def main() -> None:
    setup_logging()
    api = Api()
    ok, message = check_ollama()
    log.info("ollama check: %s — %s", "ok" if ok else "FAILED", message)
    entry = _frontend_entry()
    log.info("frontend entry: %s", entry)
    window = webview.create_window("AI Desktop Agent", entry, js_api=api, width=900, height=700)
    api.set_window(window)
    if not ok:
        # Surface the readiness problem as soon as the DOM is ready.
        def notify():
            event = {"type": "error", "turn_id": "startup", "text": message}
            window.evaluate_js(f"window.onAgentEvent && window.onAgentEvent({json.dumps(event)})")

        window.events.loaded += notify
    webview.start()


if __name__ == "__main__":
    main()
