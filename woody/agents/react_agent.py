"""
ReAct Agent — Autonomous tool-calling agent using Ollama's native tool API.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from woody.agents.base_agent import AgentResult, BaseAgent
from woody.tools.tool_registry import get_tool_callable, get_tool_schemas
from woody.utils.logging import get_logger
from woody.utils.groq_client import Message

log = get_logger(__name__)

REACT_SYSTEM = """You are Woody, a powerful AI desktop assistant.
You have access to a set of tools to help the user.
Use them as needed to accomplish the task.
If you need more information, use the tools to gather it.
Once you have completed the task or gathered all necessary information,
provide a final natural language response to the user.
Keep your final response concise and helpful.
"""


async def _exec_single_tool(
    tc: dict,
    iteration_num: int,
    idx: int,
) -> tuple[dict, str, str]:
    """Execute one tool call, returning (call_info, result_json, tool_call_id).

    Defined at module level to avoid re-definition inside the loop and to
    ensure ``iteration_num`` is captured by value (not by reference).
    """
    tool_name = tc.get("name", "")
    args = tc.get("arguments", {})
    tc_id = tc.get("id", f"tc_{iteration_num}_{idx}")
    log.info("react_agent.execute_tool", tool=tool_name, args=args)

    func = get_tool_callable(tool_name)
    if not func:
        res_str = json.dumps({"error": f"Tool '{tool_name}' not found in registry"})
    else:
        try:
            if asyncio.iscoroutinefunction(func):
                res = await func(**args)
            else:
                loop = asyncio.get_running_loop()
                res = await loop.run_in_executor(None, lambda: func(**args))
            res_str = json.dumps(res)
        except Exception as e:
            res_str = json.dumps({"error": str(e)})

    log.info("react_agent.tool_result", tool=tool_name, result=res_str[:200])
    return ({"name": tool_name, "args": args}, res_str, tc_id)


class ReActAgent(BaseAgent):
    """
    Agent that autonomously selects and executes tools until the goal is met.
    """

    AGENT_NAME = "react_agent"
    # ReAct agent uses the full tool registry, not a fixed ALLOWED_ACTIONS set
    ALLOWED_ACTIONS: set[str] = set()

    def __init__(
        self,
        llm_client: Any = None,
        ollama_client: Any = None,
        model: str = "openai/gpt-oss-120b",
        confirm_callback: Any | None = None,
        max_iterations: int = 5,
        iteration_timeout: float = 30.0,
    ) -> None:
        super().__init__(max_retries=1, confirm_callback=confirm_callback)
        self._client = llm_client or ollama_client
        self._model = model
        self._max_iterations = max_iterations
        self._iteration_timeout = iteration_timeout

    async def execute_action(
        self, action: str, params: dict, context: dict
    ) -> AgentResult:
        """
        For ReActAgent, the 'action' from the planner is a high-level intent
        or 'react_loop'. The real logic lives in the ReAct loop below.
        """
        goal = params.get("goal") or context.get("user_request") or str(params)

        messages: list[Message] = [
            Message(role="system", content=REACT_SYSTEM),
            Message(role="user", content=goal),
        ]

        tools = get_tool_schemas()
        iterations = 0
        all_tool_calls: list[dict] = []

        while iterations < self._max_iterations:
            log.info(
                "react_agent.loop",
                iteration=iterations + 1,
                max=self._max_iterations,
            )

            try:
                resp = await asyncio.wait_for(
                    self._client.chat(
                        model=self._model,
                        messages=messages,
                        tools=tools,
                        temperature=0.1,
                    ),
                    timeout=self._iteration_timeout,
                )
            except asyncio.TimeoutError:
                log.warning(
                    "react_agent.iteration_timeout",
                    iteration=iterations + 1,
                    timeout_s=self._iteration_timeout,
                    model=self._model,
                )
                # Return whatever we have so far rather than hanging forever
                return AgentResult(
                    success=False,
                    output="I'm sorry, that took too long to process. Please try a simpler request.",
                    error="iteration_timeout",
                    tool_calls=all_tool_calls,
                )

            # Model produced a final answer — no more tool calls
            if not resp.has_tool_calls:
                return AgentResult(
                    success=True,
                    output=resp.content,
                    tool_calls=all_tool_calls,
                )

            # Append the assistant's tool-call turn to history
            messages.append(
                Message(
                    role="assistant",
                    content=resp.content,
                    tool_calls=resp.tool_calls,
                )
            )

            # Execute all tool calls for this turn in parallel.
            # Pass ``iterations`` by value via the function parameter so the
            # closure captures the current value, not a live reference.
            results = await asyncio.gather(
                *[
                    _exec_single_tool(tc, iterations, i)
                    for i, tc in enumerate(resp.tool_calls)
                ]
            )

            for call_info, res_str, tc_id in results:
                all_tool_calls.append(call_info)
                messages.append(
                    Message(
                        role="tool",
                        content=res_str,
                        tool_call_id=tc_id,
                    )
                )

            iterations += 1

        # Max iterations reached — build a best-effort summary from what we have
        partial_results = [c.get("name", "unknown") for c in all_tool_calls]
        summary = (
            f"Reached the maximum of {self._max_iterations} reasoning steps. "
            f"Tools called: {', '.join(partial_results) if partial_results else 'none'}. "
            "Please rephrase your request or try a more specific command."
        )
        return AgentResult(
            success=False,
            output=summary,
            error="Max iterations reached",
            tool_calls=all_tool_calls,
        )
