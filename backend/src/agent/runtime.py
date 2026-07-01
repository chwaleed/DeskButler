"""The single long-lived asyncio loop that owns the graph. All Api calls route here."""
from __future__ import annotations

import asyncio
import threading
import uuid
from typing import Callable

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from agent.graph import build_graph

THREAD_ID = "main"


class Runtime:
    def __init__(self, emit: Callable[[dict], None]):
        self._emit = emit
        self._loop: asyncio.AbstractEventLoop | None = None
        self._graph = None
        self._busy = False
        self._current_turn: str | None = None
        self._config = {"configurable": {"thread_id": THREAD_ID}}

    def start(self) -> None:
        ready = threading.Event()

        def run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._graph = build_graph()
            ready.set()
            self._loop.run_forever()

        threading.Thread(target=run_loop, daemon=True, name="agent-loop").start()
        ready.wait(timeout=30)

    def send(self, text: str) -> str:
        if self._busy:
            return "busy"
        turn_id = uuid.uuid4().hex
        self._current_turn = turn_id
        self._busy = True
        asyncio.run_coroutine_threadsafe(self._run_turn(turn_id, text), self._loop)
        return turn_id

    def resume(self, decision: dict) -> None:
        if self._current_turn is None:
            return
        asyncio.run_coroutine_threadsafe(
            self._drive(self._current_turn, Command(resume=decision)), self._loop
        )

    def cancel(self) -> None:
        # Best-effort: mark not busy so the UI unlocks; the in-flight step still completes.
        self._busy = False
        self._current_turn = None

    async def _run_turn(self, turn_id: str, text: str) -> None:
        await self._drive(turn_id, {"messages": [HumanMessage(text)]})

    async def _drive(self, turn_id: str, payload) -> None:
        try:
            async for event in self._graph.astream_events(payload, self._config, version="v2"):
                kind = event.get("event")
                if kind == "on_tool_start":
                    name = event.get("name", "tool")
                    self._emit({"type": "step", "turn_id": turn_id, "text": f"running {name}…"})
            # After the stream, inspect state: paused (interrupt) or finished.
            state = self._graph.get_state(self._config)
            if state.tasks and any(t.interrupts for t in state.tasks):
                intr = next(t.interrupts[0] for t in state.tasks if t.interrupts)
                self._emit({"type": "approval", "turn_id": turn_id, "request": intr.value})
                return
            final = state.values["messages"][-1]
            self._emit({"type": "final", "turn_id": turn_id, "text": getattr(final, "content", "")})
            self._busy = False
        except Exception as e:  # surface as a chat bubble, never crash the loop
            self._emit({"type": "error", "turn_id": turn_id, "text": str(e)})
            self._busy = False
