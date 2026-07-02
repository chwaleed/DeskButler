"""Dev logging. Set DESKBUTLER_DEV=1 to see everything the agent does in the terminal."""
from __future__ import annotations

import logging
import os
import sys

_DEV = os.environ.get("DESKBUTLER_DEV", "").lower() in ("1", "true", "yes", "on")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"deskbutler.{name}")


def setup_logging() -> None:
    level = logging.DEBUG if _DEV else logging.INFO
    root = logging.getLogger("deskbutler")
    if root.handlers:  # already configured
        return
    # Windows consoles are often cp1252; the model emits emoji/unicode. Force UTF-8 on
    # the stream so a stray glyph in a log line never crashes a turn.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s  %(levelname)-5s  %(name)s  %(message)s", "%H:%M:%S")
    )
    root.addHandler(handler)
    root.setLevel(level)
    root.propagate = False
    if _DEV:
        root.info("dev logging ON (DESKBUTLER_DEV set) — level DEBUG")
