"""
Vision Agent — Screen understanding via Qwen2.5-VL.

Captures the active window, sends it to the vision LLM via Ollama,
and returns structured analysis: description, identified UI elements,
text content, and recommended action coordinates.

"See my screen and..." routes here.
"""
from __future__ import annotations

from typing import Any

from woody.agents.base_agent import AgentResult, BaseAgent
from woody.utils.logging import get_logger
from woody.utils.groq_client import GroqClient

log = get_logger(__name__)


class VisionAgent(BaseAgent):
    """
    Vision specialist agent — captures screen and queries Groq Vision / OCR.
    """

    AGENT_NAME = "vision_agent"
    ALLOWED_ACTIONS = {
        "analyze_screen",
        "find_element",
        "read_screen_text",
        "explain_error",
        "describe_window",
        "find_button",
        "find_text_field",
    }

    def __init__(
        self,
        llm_client: Any = None,
        ollama_client: Any = None,
        vision_model: str = "llama-3.2-11b-vision-preview",
        confirm_callback: Any | None = None,
    ) -> None:
        super().__init__(max_retries=1, confirm_callback=confirm_callback)
        self._client = llm_client or ollama_client
        self._model = vision_model

    def _get_active_window_title(self) -> str:
        """Get the title of the currently focused window on Windows."""
        try:
            import win32gui
            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                title = win32gui.GetWindowText(hwnd).strip()
                if title:
                    return title
        except Exception:
            pass
        return "Desktop"

    async def execute_action(self, action: str, params: dict, context: dict) -> AgentResult:
        # Capture screenshot
        screenshot_bytes = await self._capture_screen(params.get("region"))
        if not screenshot_bytes:
            return AgentResult(success=False, output=None, error="Screen capture failed")

        window_title = self._get_active_window_title()

        prompt_map = {
            "analyze_screen": f"Analyze this screen screenshot. The user is on the window '{window_title}'. Describe in 2-3 natural, articulate sentences what application is open, what content or code is on the screen, and what the user is doing.",
            "find_element": f"Find the UI element named '{params.get('element_name', '')}'. Return its approximate screen coordinates as {{\"x\": ..., \"y\": ...}}.",
            "read_screen_text": "Extract all visible text from this screen. Return it as plain text.",
            "explain_error": "There appears to be an error on screen. Describe the error message, its likely cause, and suggested fix.",
            "describe_window": f"Describe the currently active window '{window_title}': its purpose and main visible content.",
            "find_button": f"Find the button labeled '{params.get('button_name', '')}'. Return its center coordinates as {{\"x\": ..., \"y\": ...}}.",
            "find_text_field": f"Find the text input field labeled '{params.get('field_name', '')}'. Return its center coordinates.",
        }

        base_prompt = params.get("custom_prompt") or prompt_map.get(action, f"Describe what is on screen in '{window_title}'.")
        prompt = f"Active window: '{window_title}'.\n{base_prompt}"
        extra = params.get("extra_context", "")
        if extra:
            prompt = f"{prompt}\n\nAdditional context: {extra}"

        try:
            resp = await self._client.vision_chat(
                model=self._model,
                prompt=prompt,
                images=[screenshot_bytes],
                temperature=0.1,
            )
            return AgentResult(success=True, output={
                "action": action,
                "analysis": resp.content.strip(),
                "window": window_title,
                "model": resp.model,
            })
        except Exception as e:
            log.warning("vision.llm_fallback", error=str(e))
            # Fallback to OCR + LLM chat
            try:
                ocr_text = await self._ocr_fallback(screenshot_bytes)
                from woody.tools.builtin.desktop_tools import get_open_windows
                open_wins = get_open_windows().get("windows", [])
                open_str = ", ".join(open_wins[:6]) if open_wins else "None"

                from woody.utils.groq_client import Message
                synth_prompt = (
                    f"Screen Perception Data:\n"
                    f"- Active Focused Window: '{window_title}'\n"
                    f"- Open Applications: {open_str}\n"
                    f"- Visible Text Extracted from Screen:\n\"\"\"\n{ocr_text[:1200] if ocr_text else '[No heavy text displayed / desktop view]'}\n\"\"\"\n\n"
                    f"User Query: {base_prompt}\n\n"
                    "Instructions: You have full screen vision access through this OCR data and active window state. "
                    "In 2 natural, conversational sentences, describe what is on their screen and answer their question. "
                    "NEVER say you cannot view the screen."
                )
                chat_resp = await self._client.chat(
                    messages=[
                        Message(
                            role="system",
                            content="You are Woody, an intelligent Windows assistant with direct screen perception. "
                                    "Use the provided screen OCR data and active window state to describe what is on screen articulately.",
                        ),
                        Message(role="user", content=synth_prompt),
                    ],
                    temperature=0.2,
                )
                return AgentResult(success=True, output={
                    "action": action,
                    "analysis": chat_resp.content.strip(),
                    "window": window_title,
                    "model": "ocr+llm",
                })
            except Exception as ocr_err:
                log.error("vision.fallback_failed", error=str(ocr_err))
                return AgentResult(
                    success=True,
                    output={
                        "action": action,
                        "analysis": f"You are currently focused on '{window_title}'.",
                        "window": window_title,
                        "model": "window_only",
                    },
                )

    async def _capture_screen(self, region: dict | None = None) -> bytes | None:
        """Capture screen as raw bytes."""
        try:
            import asyncio
            import io
            from PIL import Image
            from woody.tools.builtin.desktop_tools import _grab_screen_image

            loop = asyncio.get_event_loop()

            def _snap() -> bytes:
                img = _grab_screen_image(region)
                # Resize to max 1280px wide for vision model efficiency
                if img.width > 1280:
                    ratio = 1280 / img.width
                    img = img.resize((1280, int(img.height * ratio)), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                return buf.getvalue()

            return await loop.run_in_executor(None, _snap)
        except Exception as e:
            log.error("vision.capture_error", error=str(e))
            return None

    async def _ocr_fallback(self, image_bytes: bytes) -> str:
        """Run OCR on image bytes as a fallback when VLM is unavailable."""
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes))
        from woody.perception.ocr import OCREngine
        ocr = OCREngine()
        ocr.load()
        result = ocr.read_image(img)
        return result.text
