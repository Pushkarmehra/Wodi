"""
Dispatch Bus — Routes subtasks to specialist agents.

Takes a list of SubTask objects from the Planner, dispatches each to the
appropriate agent (respecting dependencies), collects results, and feeds
them to the Critic for verification.

Supports parallel execution of independent subtasks (no shared dependencies).
"""
from __future__ import annotations

import asyncio
from typing import Any

from wodi.agents.base_agent import AgentResult
from wodi.agents.desktop_agent import DesktopAgent
from wodi.agents.vision_agent import VisionAgent
from wodi.agents.system_agent import SystemAgent
from wodi.agents.browser_agent import BrowserAgent
from wodi.agents.coding_agent import CodingAgent
from wodi.agents.react_agent import ReActAgent
from wodi.critic.critic import Critic
from wodi.planner.working_memory import (
    SubTask,
    WorkingMemoryState,
    get_pending_subtasks,
    is_all_done,
    mark_subtask_done,
    mark_subtask_failed,
)
from wodi.utils.logging import get_logger

log = get_logger(__name__)


class DispatchBus:
    """
    Dispatch bus routing subtasks to the correct specialist agent.

    Usage:
        bus = DispatchBus(agents={...}, critic=critic)
        await bus.execute(state)
        # state["agent_results"] now populated
    """

    def __init__(
        self,
        agents: dict[str, Any],
        critic: Critic | None = None,
        max_parallel: int = 3,
    ) -> None:
        self._agents = agents
        self._critic = critic
        self._max_parallel = max_parallel

    async def execute(self, state: WorkingMemoryState) -> WorkingMemoryState:
        """
        Execute all subtasks in dependency order with parallelism where possible.
        Modifies state in-place.
        """
        max_rounds = 20  # Safety limit to prevent infinite loops
        rounds = 0

        while not is_all_done(state) and rounds < max_rounds:
            ready = get_pending_subtasks(state)
            if not ready:
                break

            # Execute up to max_parallel ready subtasks concurrently
            batch = ready[: self._max_parallel]
            log.info(
                "dispatch.batch",
                n=len(batch),
                tasks=[t["id"] for t in batch],
            )

            # Mark all as running
            for task in batch:
                task["status"] = "running"

            # Execute concurrently
            results = await asyncio.gather(
                *[self._execute_task(task, state) for task in batch],
                return_exceptions=True,
            )

            # Process results
            for task, result in zip(batch, results):
                if isinstance(result, Exception):
                    mark_subtask_failed(state, task["id"], str(result))
                    log.error(
                        "dispatch.task_exception",
                        task_id=task["id"],
                        error=str(result),
                    )
                elif result.success:
                    mark_subtask_done(state, task["id"], result.output)
                else:
                    mark_subtask_failed(state, task["id"], result.error or "Unknown error")

            rounds += 1

        if rounds >= max_rounds:
            log.warning("dispatch.max_rounds_reached", rounds=rounds)

        log.info(
            "dispatch.complete",
            done=sum(1 for t in state["subtasks"] if t["status"] == "done"),
            failed=sum(1 for t in state["subtasks"] if t["status"] == "failed"),
        )
        return state

    async def _execute_task(self, task: SubTask, state: WorkingMemoryState) -> AgentResult:
        """Execute a single subtask via the appropriate agent."""
        agent_name = task["agent"]
        agent = self._agents.get(agent_name)

        if agent is None:
            log.warning("dispatch.agent_not_found", agent=agent_name, fallback="system_agent")
            agent = self._agents.get("system_agent")

        if agent is None:
            return AgentResult(
                success=False,
                output=None,
                error=f"No agent found for '{agent_name}'",
            )

        # Build context from current state
        context = {
            "session_id": state["session_id"],
            "screen_context": state.get("screen_context", ""),
            "user_request": state.get("user_request", ""),
            "agent_results": state.get("agent_results", {}),
        }

        # LLM-based agents (react_agent, vision_agent) need a much longer timeout
        # than fast tool agents (system_agent, desktop_agent).  Local Ollama inference
        # on consumer hardware can take 60–120 s for a 7B model, so we give it 180 s
        # and keep a short 45 s timeout for pure tool dispatches.
        LLM_AGENTS = {"react_agent", "vision_agent", "coding_agent", "browser_agent"}
        timeout_seconds = 180.0 if agent_name in LLM_AGENTS else 45.0

        log.info(
            "dispatch.task_start",
            task_id=task["id"],
            agent=agent_name,
            action=task["action"],
            timeout_s=timeout_seconds,
        )

        result = await agent.run(
            action=task["action"],
            params=task["params"],
            timeout_seconds=timeout_seconds,
            context=context,
            critic=self._critic,
            goal_description=task["description"],
        )

        log.info(
            "dispatch.task_done",
            task_id=task["id"],
            success=result.success,
            elapsed_ms=f"{result.elapsed_ms:.0f}",
        )
        return result


def build_dispatch_bus(
    config: Any,
    llm_client: Any = None,
    ollama_client: Any = None,
    confirm_callback: Any | None = None,
    critic: Critic | None = None,
) -> DispatchBus:
    """Factory function to build the DispatchBus with all configured agents."""
    client = llm_client or ollama_client
    agents: dict[str, Any] = {}

    if config.agents.desktop_enabled:
        agents["desktop_agent"] = DesktopAgent(confirm_callback=confirm_callback)

    if config.agents.vision_enabled and config.models.vision:
        agents["vision_agent"] = VisionAgent(
            llm_client=client,
            vision_model=config.models.vision,
            confirm_callback=confirm_callback,
        )

    if config.agents.system_enabled:
        agents["system_agent"] = SystemAgent(confirm_callback=confirm_callback)

    if config.agents.browser_enabled:
        agents["browser_agent"] = BrowserAgent(confirm_callback=confirm_callback)

    if config.agents.coding_enabled:
        agents["coding_agent"] = CodingAgent(confirm_callback=confirm_callback)

    if client:
        agents["react_agent"] = ReActAgent(
            llm_client=client,
            model=config.models.planner,
            confirm_callback=confirm_callback,
        )

    log.info("dispatch.agents_ready", agents=list(agents.keys()))
    return DispatchBus(agents=agents, critic=critic)
