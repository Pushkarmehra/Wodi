"""
Vision Agent — Screen understanding via Qwen2.5-VL.

Captures the active window, sends it to the vision LLM via Ollama,
and returns structured analysis: description, identified UI elements,
text content, and recommended action coordinates.

"See my screen and..." routes here.
"""
from __future__ import annotations

from typing import Any

from wodi.agents.base_agent import AgentResult, BaseAgent
from wodi.utils.logging import get_logger
from wodi.utils.ollama_client import OllamaClient

log = get_logger(__name__)


class VisionAgent(BaseAgent):
    """
    Vision specialist agent — captures screen and queries Qwen2.5-VL.
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
        ollama_client: OllamaClient,
        vision_model: str = "qwen2.5vl:3b",
        confirm_callback: Any | None = None,
    ) -> None:
        super().__init__(max_retries=1, confirm_callback=confirm_callback)
        self._client = ollama_client
        self._model = vision_model

    async def execute_action(self, action: str, params: dict, context: dict) -> AgentResult:
        # Capture screenshot
        screenshot_bytes = await self._capture_screen(params.get("region"))
        if not screenshot_bytes:
            return AgentResult(success=False, output=None, error="Screen capture failed")

        prompt_map = {
            "analyze_screen": "Analyze this screen. Describe what application is open, what's visible, and what the user might want to do next.",
            "find_element": f"Find the UI element named '{params.get('element_name', '')}'. Return its approximate screen coordinates as {{\"x\": ..., \"y\": ...}}.",
            "read_screen_text": "Extract all visible text from this screen. Return it as plain text.",
            "explain_error": "There appears to be an error on screen. Describe the error message, its likely cause, and suggested fix.",
            "describe_window": "Describe the currently active window: its title, purpose, and main content.",
            "find_button": f"Find the button labeled '{params.get('button_name', '')}'. Return its center coordinates as {{\"x\": ..., \"y\": ...}}.",
            "find_text_field": f"Find the text input field labeled '{params.get('field_name', '')}'. Return its center coordinates.",
        }

        prompt = params.get("custom_prompt") or prompt_map.get(action, "Describe this screen.")
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
                "analysis": resp.content,
                "model": resp.model,
            })
        except Exception as e:
            log.error("vision.llm_error", error=str(e))
            # Fallback to OCR-only if VLM fails
            try:
                ocr_text = await self._ocr_fallback(screenshot_bytes)
                return AgentResult(success=True, output={
                    "action": action,
                    "analysis": f"[OCR fallback — VLM unavailable]\n{ocr_text}",
                    "model": "ocr",
                })
            except Exception as ocr_err:
                return AgentResult(success=False, output=None, error=str(e))

    async def _capture_screen(self, region: dict | None = None) -> bytes | None:
        """Capture screen as raw bytes."""
        try:
            import asyncio
            import io
            import mss
            from PIL import Image

            loop = asyncio.get_event_loop()

            def _snap() -> bytes:
                with mss.mss() as sct:
                    mon = region or sct.monitors[1]
                    shot = sct.grab(mon)
                    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
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
        from wodi.perception.ocr import OCREngine
        ocr = OCREngine()
        ocr.load()
        result = ocr.read_image(img)
        return result.text
