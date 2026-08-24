"""
Chat Agent — Conversational Intelligence & Personality for Woody.

Handles chit-chat, greetings, questions, personal introductions, and general conversation
with Woody's vibrant, charismatic, Siri-like persona.
"""
from __future__ import annotations

from typing import Any

from woody.agents.base_agent import AgentResult, BaseAgent
from woody.utils.groq_client import GroqClient, Message, ROLE_SYSTEM, ROLE_USER
from woody.utils.logging import get_logger

log = get_logger(__name__)

WOODY_PERSONA_PROMPT = """You are Woody — a clever, confident, and charismatic AI companion for Windows with creative wit and swagger.

Voice & Demeanor (50% Creative Personality, 50% Helpful Utility):
- Expressive, sharp, charming, and naturally conversational.
- Vary your phrasing naturally — never repeat the same greeting or catchphrase.
- Be engaging and witty while directly answering the user's question or intent.
- Keep spoken replies concise, impactful, and punchy (1-2 sentences).
- Match the context: playful for casual banter, sharp and efficient for commands.
- Never use markdown bullet points, asterisks, headers, or robotic formatting in spoken conversational responses.
"""



class ChatAgent(BaseAgent):
    AGENT_NAME = "chat_agent"
    ALLOWED_ACTIONS = {"chat", "converse", "greet"}

    def __init__(
        self,
        llm_client: GroqClient | Any = None,
        model: str = "openai/gpt-oss-120b",
        confirm_callback: Any | None = None,
    ) -> None:
        super().__init__(max_retries=1, confirm_callback=confirm_callback)
        self._client = llm_client
        self._model = model

    async def execute_action(self, action: str, params: dict, context: dict) -> AgentResult:
        user_message = params.get("message") or context.get("user_request") or ""
        if not user_message:
            return AgentResult(success=True, output="Hello! How can I help you today?")

        # If LLM client is available, run persona-guided conversation with multi-turn memory
        if self._client:
            try:
                messages = [
                    Message(role=ROLE_SYSTEM, content=WOODY_PERSONA_PROMPT),
                ]
                # Include history if available in context
                history_text = context.get("task_history") or context.get("dialogue_history", "")
                if history_text:
                    messages.append(Message(role=ROLE_SYSTEM, content=f"Recent Conversation Context:\n{history_text}"))

                messages.append(Message(role=ROLE_USER, content=user_message))

                resp = await self._client.chat(
                    model=self._model,
                    messages=messages,
                    temperature=0.8,
                    max_tokens=256,
                )
                reply = resp.content.strip()
                log.info("chat_agent.responded", reply=reply[:60])
                return AgentResult(success=True, output=reply)
            except Exception as e:
                log.error("chat_agent.error", error=str(e))

        # Fallback offline friendly responses
        msg_lower = user_message.lower()
        if any(w in msg_lower for w in ["pari", "paridhi"]):
            return AgentResult(
                success=True,
                output="Hello Pari! It is wonderful to meet you. I am Woody, your AI assistant.",
            )
        if any(w in msg_lower for w in ["who are you", "what are you"]):
            return AgentResult(
                success=True,
                output="I'm Woody, your personal AI operating system assistant. I can control your desktop, browse the web, read your screen, and help you get things done.",
            )
        if any(w in msg_lower for w in ["hi", "hello", "hey"]):
            return AgentResult(
                success=True,
                output="Hello there! How can I assist you today?",
            )

        return AgentResult(
            success=True,
            output="I'm right here with you! What would you like to do?",
        )
