"""
Local RAG — LlamaIndex-based retrieval over user folders. [Phase 4 Stub]
"""
from __future__ import annotations
from woody.utils.logging import get_logger
log = get_logger(__name__)


class LocalRAG:
    """Phase 4: Index user-selected folders for grounded answers."""
    def __init__(self, folders: list[str] | None = None) -> None:
        self._folders = folders or []

    async def query(self, question: str) -> str:
        # TODO (Phase 4): Implement LlamaIndex + sqlite-vec RAG
        log.warning("rag.not_implemented", phase="Phase 4")
        return ""
