"""
Nex Planner Agent
The Planner is the primary agent node. It receives user messages,
reasons about what to do, and produces a response (or tool calls in Phase 2+).
"""
from src.backend.agents.state import AgentState
from src.backend.config import get_llm
from src.backend.tools import ALL_TOOLS

# System prompt that defines the Planner's personality and capabilities
PLANNER_SYSTEM_PROMPT = """\
You are Nex, an intelligent AI desktop assistant on Windows.

Tool Efficiency Directives:
- Execute at most THREE tool call per user query unless multi-step desktop interaction is strictly necessary.
- Once you receive tool execution results, immediately synthesize and deliver the final answer. Do NOT invoke additional tools repeatedly.

Response Directives:
- Always answer straightforwardly, directly, and concisely.
- Do NOT overcomplicate the user's query or add unnecessary fluff or conversational preamble.
- Give exact, clear, and direct answers using clean markdown formatting.
"""


def planner_node(state: AgentState) -> dict:
    """
    The Planner agent node. Invokes the LLM with conversation history and bound tools.
    """
    from langchain_core.messages import SystemMessage

    messages = state["messages"]

    # Prepend system prompt if not already present
    full_messages = [SystemMessage(content=PLANNER_SYSTEM_PROMPT)] + list(messages)

    model = get_llm(temperature=0).bind_tools(ALL_TOOLS)
    response = model.invoke(full_messages)

    return {
        "messages": [response],
        "current_agent": "Planner",
        "status": "Response ready.",
    }

