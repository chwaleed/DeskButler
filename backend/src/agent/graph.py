"""LangGraph agent loop: call_model -> safety_gate -> tools -> call_model."""
from __future__ import annotations

from typing import Literal

from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt

from agent.prompts import system_prompt
from agent.safety import dry_run, is_destructive
from agent.settings import load_settings
from agent.tools import TOOLS


def _default_model():
    from langchain_ollama import ChatOllama

    return ChatOllama(model=load_settings().model)


def build_graph(model=None, checkpointer=None):
    model = model if model is not None else _default_model()
    bound = model.bind_tools(TOOLS)
    prompt = system_prompt(load_settings().allowed_roots)

    def call_model(state: MessagesState):
        msgs = state["messages"]
        if not any(isinstance(m, SystemMessage) for m in msgs):
            msgs = [SystemMessage(prompt), *msgs]
        return {"messages": [bound.invoke(msgs)]}

    def route_after_model(state: MessagesState) -> Literal["safety_gate", "__end__"]:
        return "safety_gate" if state["messages"][-1].tool_calls else END

    def safety_gate(state: MessagesState):
        last = state["messages"][-1]
        rejections = []
        for call in last.tool_calls:
            if is_destructive(call["name"]) and not dry_run():
                decision = interrupt(
                    {"tool": call["name"], "args": call["args"], "message": f"Approve {call['name']}?"}
                )
                if isinstance(decision, dict) and decision.get("decision") == "reject":
                    rejections.append(
                        ToolMessage(content="Rejected by user.", tool_call_id=call["id"])
                    )
        # ponytail: partial mixes (some approved, some rejected in one message) aren't
        # fully handled — ToolNode would still run every tool_call. Fine for the 2-tool
        # base (single move_file per turn); revisit when a second destructive tool lands.
        return {"messages": rejections}

    def route_after_gate(state: MessagesState) -> Literal["tools", "call_model"]:
        # If the last message is a ToolMessage (all rejected), skip ToolNode and let the model react.
        last = state["messages"][-1]
        if isinstance(last, ToolMessage):
            return "call_model"
        return "tools"

    g = StateGraph(MessagesState)
    g.add_node("call_model", call_model)
    g.add_node("safety_gate", safety_gate)
    g.add_node("tools", ToolNode(TOOLS))
    g.add_edge(START, "call_model")
    g.add_conditional_edges("call_model", route_after_model, {"safety_gate": "safety_gate", END: END})
    g.add_conditional_edges("safety_gate", route_after_gate, {"tools": "tools", "call_model": "call_model"})
    g.add_edge("tools", "call_model")
    return g.compile(checkpointer=checkpointer)
