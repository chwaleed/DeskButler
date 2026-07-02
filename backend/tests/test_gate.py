import pytest
from pathlib import Path
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agent.graph import build_graph


class FakeToolModel(GenericFakeChatModel):
    """GenericFakeChatModel can't bind_tools (raises NotImplementedError), so we
    override bind_tools to just replay the queued messages, tool_calls included."""

    def bind_tools(self, tools, **kwargs):
        return self


def _model_that_moves_then_answers():
    """Fake model: first turn requests a move_file tool call, second turn answers."""
    move_call = AIMessage(
        content="",
        tool_calls=[{"name": "move_file", "args": {"src": "a", "dst": "b"}, "id": "call1"}],
    )
    done = AIMessage(content="Done.")
    return FakeToolModel(messages=iter([move_call, done]))


def test_destructive_call_pauses_for_approval(monkeypatch):
    # Stub the tool executor so no real filesystem work happens.
    # Patch names where they are USED, not where they are defined.
    monkeypatch.setattr("agent.tools.shutil.move", lambda a, b: None)
    monkeypatch.setattr("agent.tools.resolve_allowed", lambda p, roots=None: Path(p))
    monkeypatch.setattr("agent.graph.dry_run", lambda: False)

    graph = build_graph(model=_model_that_moves_then_answers(), checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "t1"}}
    graph.invoke({"messages": [HumanMessage("move a to b")]}, config)
    # Graph should be interrupted, not finished.
    state = graph.get_state(config)
    assert state.next  # there is a pending node -> we are paused
    assert state.tasks and any(t.interrupts for t in state.tasks)  # an interrupt is outstanding


def test_reject_short_circuits_without_moving(monkeypatch):
    moved = {"called": False}
    def fake_move(a, b):
        moved["called"] = True
    monkeypatch.setattr("agent.tools.shutil.move", fake_move)
    monkeypatch.setattr("agent.tools.resolve_allowed", lambda p, roots=None: Path(p))
    monkeypatch.setattr("agent.graph.dry_run", lambda: False)

    graph = build_graph(model=_model_that_moves_then_answers(), checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "t2"}}
    graph.invoke({"messages": [HumanMessage("move a to b")]}, config)
    final = graph.invoke(Command(resume={"decision": "reject"}), config)
    assert moved["called"] is False
    # The conversation continued to a final answer after rejection.
    assert any(getattr(m, "content", "") == "Done." for m in final["messages"])


def test_approve_executes_the_move(monkeypatch):
    moved = {"called": False}
    def fake_move(a, b):
        moved["called"] = True
    monkeypatch.setattr("agent.tools.shutil.move", fake_move)
    monkeypatch.setattr("agent.tools.Path.exists", lambda self: False)
    monkeypatch.setattr("agent.tools.resolve_allowed", lambda p, roots=None: Path(p))
    monkeypatch.setattr("agent.graph.dry_run", lambda: False)

    graph = build_graph(model=_model_that_moves_then_answers(), checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "t3"}}
    graph.invoke({"messages": [HumanMessage("move a to b")]}, config)
    final = graph.invoke(Command(resume={"decision": "approve"}), config)
    assert moved["called"] is True
    assert any(getattr(m, "content", "") == "Done." for m in final["messages"])


def _model_that_batch_moves_then_answers():
    call = AIMessage(
        content="",
        tool_calls=[{
            "name": "batch_move",
            "args": {"moves": [{"src": "a.txt", "dst": "s/a.txt"}]},
            "id": "call1",
        }],
    )
    return FakeToolModel(messages=iter([call, AIMessage(content="Done.")]))


def test_batch_move_pauses_for_approval(monkeypatch):
    monkeypatch.setattr("agent.graph.dry_run", lambda: False)
    graph = build_graph(model=_model_that_batch_moves_then_answers(), checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "t4"}}
    graph.invoke({"messages": [HumanMessage("organize my downloads")]}, config)
    state = graph.get_state(config)
    assert state.next
    assert state.tasks and any(t.interrupts for t in state.tasks)
