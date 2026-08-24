"""
Nex Agent State Definition
Defines the shared state that flows through the LangGraph state machine.
"""
from typing import TypedDict, Annotated, Literal
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    The central state object passed between all nodes in the LangGraph.
    
    Attributes:
        messages: The conversation message history. Uses LangGraph's
                  add_messages reducer to automatically append new messages.
        current_agent: Display name of the currently active agent
                       (e.g., "Planner", "File Agent").
        status: A short human-readable status string for the UI
                (e.g., "Planning next steps...", "Creating folder...").
    """
    messages: Annotated[list[BaseMessage], add_messages]
    current_agent: str
    status: str
