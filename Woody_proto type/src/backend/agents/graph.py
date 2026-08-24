"""
Nex LangGraph Definition
Compiles the multi-agent state graph. In Phase 1, this is a single-node
graph (Planner only). Nodes and edges will be added in subsequent phases.
"""
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition

from src.backend.agents.state import AgentState
from src.backend.agents.planner import planner_node
from src.backend.tools import ALL_TOOLS


def build_graph():
    """
    Constructs and compiles the LangGraph state machine with Tool execution.
    
    Graph flow:
        START -> planner -> (tools_condition) -> tools -> planner
                         -> END
    """
    builder = StateGraph(AgentState)

    # ── Nodes ──
    builder.add_node("planner", planner_node)
    builder.add_node("tools", ToolNode(ALL_TOOLS))

    # ── Edges ──
    builder.add_edge(START, "planner")

    # If the model emits tool calls, route to "tools" node, otherwise route to END
    builder.add_conditional_edges("planner", tools_condition)

    # After executing tools, return to planner node for follow-up reasoning/response
    builder.add_edge("tools", "planner")

    return builder.compile()


# Compile the graph once at module load
graph = build_graph()
