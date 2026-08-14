"""
Structured logging setup for Wodi using structlog + rich.

Usage:
    from wodi.utils.logging import get_logger
    log = get_logger(__name__)
    log.info("kernel.start", tier="standard", model="qwen2.5:7b")
"""
from __future__ import annotations

import logging
import sys

import structlog
from rich.console import Console
from rich.logging import RichHandler

_initialized = False
_console = Console(stderr=True)


def setup_logging(level: str = "INFO") -> None:
    """Configure structlog + standard logging with Rich output."""
    global _initialized
    if _initialized:
        return

    log_level = getattr(logging, level.upper(), logging.INFO)

    # Standard library logging → Rich handler
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=_console, rich_tracebacks=True, markup=True)],
    )

    # Suppress noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "charset_normalizer", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    def safe_add_logger_name(logger: object, method_name: str, event_dict: dict) -> dict:
        """Safe version of add_logger_name that handles PrintLogger (no .name attr)."""
        name = getattr(logger, "name", None)
        if name:
            event_dict["logger"] = name
        return event_dict

    # structlog configuration
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            safe_add_logger_name,
            structlog.processors.TimeStamper(fmt="%H:%M:%S", utc=False),
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    _initialized = True


def get_logger(name: str) -> structlog.BoundLogger:
    """Return a bound structlog logger for the given module name."""
    if not _initialized:
        setup_logging()
    return structlog.get_logger(name)
