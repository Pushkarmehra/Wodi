"""Unit tests for ChatAgent persona and conversational responses."""
from __future__ import annotations

import pytest
from woody.agents.chat_agent import ChatAgent


class TestChatAgent:
    @pytest.mark.asyncio
    async def test_chat_agent_fallback_pari_greeting(self):
        agent = ChatAgent(llm_client=None)
        res = await agent.execute_action("chat", {"message": "hi say hello to pari"}, {})
        assert res.success
        assert "Pari" in res.output or "Hello" in res.output

    @pytest.mark.asyncio
    async def test_chat_agent_fallback_identity(self):
        agent = ChatAgent(llm_client=None)
        res = await agent.execute_action("chat", {"message": "who are you"}, {})
        assert res.success
        assert "Woody" in res.output
