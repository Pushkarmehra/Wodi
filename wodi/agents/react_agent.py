"""
ReAct Agent — Autonomous tool-calling agent using Ollama's native tool API.
"""
from __future__ import annotations

import json
import time
from typing import Any

from wodi.agents.base_agent import AgentResult, BaseAgent
from wodi.tools.tool_registry import get_tool_callable, get_tool_schemas
from wodi.utils.logging import get_logger
from wodi.utils.ollama_client import Message

log = get_logger(__name__)

REACT_SYSTEM = """You are Wodi, a powerful local AI assistant.
You have access to a set of tools to help the user.
Use them as needed to accomplish the task.
If you need more information, use the tools to gather it.
Once you have completed the task or gathered all necessary information, 
provide a final natural language response to the user.
Keep your final response concise and helpful.
"""

class ReActAgent(BaseAgent):
    """
    Agent that autonomously selects and executes tools until the goal is met.
    """
    AGENT_NAME = "react_agent"
    # ReAct agent doesn't have a fixed set of ALLOWED_ACTIONS, it uses the registry
    ALLOWED_ACTIONS = set() 

    def __init__(
        self,
        ollama_client: Any,
        model: str = "qwen2.5:7b",
        confirm_callback: Any | None = None,
        max_iterations: int = 10,
    ) -> None:
        super().__init__(max_retries=1, confirm_callback=confirm_callback)
        self._client = ollama_client
        self._model = model
        self._max_iterations = max_iterations

    async def execute_action(self, action: str, params: dict, context: dict) -> AgentResult:
        """
        For ReActAgent, the 'action' from the planner is often a high-level intent
        or just 'react_loop'. The real logic is in the loop below.
        """
        # The goal is passed via context or params if it's a direct task
        goal = params.get("goal") or context.get("user_request") or str(params)
        
        messages = [
            Message(role="system", content=REACT_SYSTEM),
            Message(role="user", content=goal),
        ]
        
        tools = get_tool_schemas()
        iterations = 0
        all_tool_calls = []
        
        while iterations < self._max_iterations:
            log.info("react_agent.loop", iteration=iterations + 1, max=self._max_iterations)
            
            resp = await self._client.chat(
                model=self._model,
                messages=messages,
                tools=tools,
                temperature=0.1,
            )
            
            # If the model didn't call any tools, it's done!
            if not resp.has_tool_calls:
                return AgentResult(
                    success=True,
                    output=resp.content,
                    tool_calls=all_tool_calls,
                )
                
            # Add the assistant's tool call message to the history
            messages.append(Message(
                role="assistant",
                content=resp.content,
                tool_calls=resp.tool_calls
            ))
            
            async def _exec_single_tool(tc: dict, idx: int) -> tuple[dict, str, str]:
                tool_name = tc.get("name", "")
                args = tc.get("arguments", {})
                tc_id = tc.get("id", f"tc_{iterations}_{idx}")
                log.info("react_agent.execute_tool", tool=tool_name, args=args)
                func = get_tool_callable(tool_name)
                if not func:
                    res_str = json.dumps({"error": f"Tool {tool_name} not found"})
                else:
                    try:
                        if asyncio.iscoroutinefunction(func):
                            res = await func(**args)
                        else:
                            loop = asyncio.get_event_loop()
                            res = await loop.run_in_executor(None, lambda: func(**args))
                        res_str = json.dumps(res)
                    except Exception as e:
                        res_str = json.dumps({"error": str(e)})
                log.info("react_agent.tool_result", tool=tool_name, result=res_str[:100])
                return ({"name": tool_name, "args": args}, res_str, tc_id)

            # Execute tools in parallel
            import asyncio
            results = await asyncio.gather(*[_exec_single_tool(tc, i) for i, tc in enumerate(resp.tool_calls)])
            
            for call_info, res_str, tc_id in results:
                all_tool_calls.append(call_info)
                messages.append(Message(
                    role="tool",
                    content=res_str,
                    tool_call_id=tc_id,
                ))
                
            iterations += 1
            
        return AgentResult(
            success=False,
            output="Max iterations reached without a final answer.",
            error="Max iterations reached",
            tool_calls=all_tool_calls,
        )
