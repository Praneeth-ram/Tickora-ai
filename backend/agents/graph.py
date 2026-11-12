from functools import lru_cache
from langgraph.graph import END, StateGraph  # pyright: ignore[reportMissingImports]
from backend.agents.nodes import (
    compound_node,
    context_node,
    correction_node,
    error_node,
    execution_node,
    greeting_node,
    planning_node,
    route_after_context,
    route_request,
    route_validation,
    supervisor_node,
)
from backend.agents.state import ChatState


@lru_cache(maxsize=1)
def get_chat_graph():
    graph = StateGraph(ChatState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("greeting", greeting_node)
    graph.add_node("context", context_node)
    graph.add_node("planning", planning_node)
    graph.add_node("correction", correction_node)
    graph.add_node("execution", execution_node)
    graph.add_node("controlled_error", error_node)
    graph.add_node("compound", compound_node)

    graph.set_entry_point("supervisor")

    graph.add_conditional_edges(
        "supervisor",
        route_request,
        {
            "greeting": "greeting",
            "compound": "compound",
            "query": "context",
            "third_party": "controlled_error",
            "unsupported": "controlled_error",
            "write_request": "controlled_error",
        },
    )
    graph.add_conditional_edges(
        "context",
        route_after_context,
        {"done": END, "plan": "planning"},
    )
    graph.add_edge("planning", "correction")
    graph.add_conditional_edges(
        "correction",
        route_validation,
        {
            "ok": "execution",
            "invalid": "controlled_error",
        },
    )

    graph.add_edge("greeting", END)
    graph.add_edge("execution", END)
    graph.add_edge("controlled_error", END)
    graph.add_edge("compound", END)

    return graph.compile()