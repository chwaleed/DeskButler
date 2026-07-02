"""The single long-lived asyncio loop that owns the graph. All Api calls route here."""
from __future__ import annotations

import asyncio
import threading
import uuid
from typing import Callable

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from agent.graph import build_graph
from agent.logs import get_logger
from agent.settings import app_data_dir

log = get_logger("runtime")

class Runtime:
    def __init__(self, emit: Callable[[dict], None]):
        self._emit = emit
        self._loop: asyncio.AbstractEventLoop | None = None
        self._graph = None
        self._saver_cm = None
        self._busy = False
        self._current_turn: str | None = None
        # A fresh conversation each app start, so old sessions don't pile into the
        # model's context. new_chat() rolls a new one on demand.
        self._thread_id = uuid.uuid4().hex

    @property
    def _config(self) -> dict:
        return {"configurable": {"thread_id": self._thread_id}, "recursion_limit": 50}

    def new_chat(self) -> None:
        """Start a fresh conversation (clean context for the model)."""
        self._thread_id = uuid.uuid4().hex
        self._busy = False
        self._current_turn = None
        log.info("new chat — thread=%s", self._thread_id[:8])

    def start(self) -> None:
        ready = threading.Event()

        def run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._setup())
            ready.set()
            self._loop.run_forever()

        threading.Thread(target=run_loop, daemon=True, name="agent-loop").start()
        ready.wait(timeout=30)

    async def _setup(self) -> None:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        # Enter the async saver's context and keep it open for the loop's lifetime.
        self._saver_cm = AsyncSqliteSaver.from_conn_string(str(app_data_dir() / "checkpoints.db"))
        saver = await self._saver_cm.__aenter__()
        self._graph = build_graph(checkpointer=saver)
        log.info("runtime ready — graph compiled on worker loop")

    def send(self, text: str) -> str:
        if self._busy:
            log.warning("send() ignored — a turn is already in flight")
            return "busy"
        turn_id = uuid.uuid4().hex
        self._current_turn = turn_id
        self._busy = True
        log.info("send turn=%s text=%r", turn_id[:8], text)
        asyncio.run_coroutine_threadsafe(self._run_turn(turn_id, text), self._loop)
        return turn_id

    def resume(self, decision: dict) -> None:
        if self._current_turn is None:
            return
        log.info("resume turn=%s decision=%r", self._current_turn[:8], decision)
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
                    args = (event.get("data") or {}).get("input")
                    log.info("tool start: %s args=%s", name, args)
                    self._emit({"type": "step", "turn_id": turn_id, "text": f"running {name}…"})
                elif kind == "on_tool_end":
                    name = event.get("name", "tool")
                    out = str((event.get("data") or {}).get("output", ""))
                    log.info("tool end: %s -> %s", name, out[:200])
            # After the stream, inspect state: paused (interrupt) or finished.
            state = await self._graph.aget_state(self._config)
            if state.tasks and any(t.interrupts for t in state.tasks):
                intr = next(t.interrupts[0] for t in state.tasks if t.interrupts)
                log.info("PAUSED for approval: %s", intr.value)
                self._emit({"type": "approval", "turn_id": turn_id, "request": intr.value})
                return
            final = state.values["messages"][-1]
            log.info("turn %s done: %r", turn_id[:8], str(getattr(final, "content", ""))[:200])
            self._emit({"type": "final", "turn_id": turn_id, "text": getattr(final, "content", "")})
            self._busy = False
        except Exception as e:  # surface as a chat bubble, never crash the loop
            log.exception("turn %s FAILED", turn_id[:8])
            self._emit({"type": "error", "turn_id": turn_id, "text": str(e)})
            self._busy = False
