"""
Tool Registry — Dynamically generates OpenAI-compatible tool schemas for built-in tools.
"""
from __future__ import annotations

import inspect
import threading
from typing import Any, Callable

from woody.tools.builtin import browser_tools, desktop_tools, filesystem_tools, system_tools
from woody.utils.logging import get_logger

log = get_logger(__name__)

# Map of all built-in modules
BUILTIN_MODULES = [
    desktop_tools,
    system_tools,
    filesystem_tools,
    browser_tools,
]

_TOOL_MAP: dict[str, Callable] = {}
_TOOL_SCHEMAS: list[dict] = []
_REGISTRY_LOCK = threading.Lock()


def _python_type_to_json_schema(py_type: Any) -> str:
    """Map Python annotation types to JSON schema type strings."""
    # Handle inspect.Parameter.empty (no annotation provided)
    if py_type is inspect.Parameter.empty:
        return "string"  # conservative fallback
    origin = getattr(py_type, "__origin__", None)
    if origin is not None:
        # Generic aliases like list[str], dict[str, Any] — use the origin
        py_type = origin
    name = getattr(py_type, "__name__", "")
    if py_type is str or name == "str":
        return "string"
    if py_type is int or name == "int":
        return "integer"
    if py_type is float or name == "float":
        return "number"
    if py_type is bool or name == "bool":
        return "boolean"
    if py_type is dict or name == "dict":
        return "object"
    if py_type is list or name == "list":
        return "array"
    return "string"


def _parse_docstring_args(doc: str) -> dict[str, str]:
    """
    Parse parameter descriptions from a Google-style docstring.

    Example::

        Args:
            query: The search query string.
            top_n: Number of results to return.
    """
    param_docs: dict[str, str] = {}
    if not doc:
        return param_docs

    in_args = False
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped.lower() in ("args:", "arguments:", "parameters:"):
            in_args = True
            continue
        if in_args:
            # Stop at the next section header (e.g. "Returns:", "Raises:")
            if stripped and not stripped.startswith(" ") and stripped.endswith(":"):
                in_args = False
                continue
            # Param line: "    name: description" or "    name (type): description"
            if ":" in stripped:
                parts = stripped.split(":", 1)
                param_name = parts[0].strip().split("(")[0].strip()
                description = parts[1].strip()
                if param_name:
                    param_docs[param_name] = description
    return param_docs


def init_registry() -> None:
    """Initialize the registry by introspecting built-in tools.

    Thread-safe: protected by a module-level lock so concurrent callers
    (e.g. from the ReActAgent spawning parallel tool executions) don't
    produce duplicate or inconsistent schema lists.
    """
    global _TOOL_MAP, _TOOL_SCHEMAS

    # Fast-path: already initialized (double-checked locking)
    if _TOOL_MAP:
        return

    with _REGISTRY_LOCK:
        # Re-check inside the lock in case another thread initialised first
        if _TOOL_MAP:
            return

        tool_map: dict[str, Callable] = {}
        tool_schemas: list[dict] = []

        for mod in BUILTIN_MODULES:
            if not hasattr(mod, "TOOLS"):
                log.warning("tool_registry.missing_TOOLS", module=mod.__name__)
                continue

            tools_list = mod.TOOLS
            # Accept both list (preferred, ordered) and set (legacy)
            if isinstance(tools_list, set):
                tools_list = sorted(tools_list)  # deterministic ordering

            for tool_name in tools_list:
                func = getattr(mod, tool_name, None)
                if hasattr(func, "func") and callable(getattr(func, "func")):
                    func = func.func

                if not func or not callable(func):
                    log.warning(
                        "tool_registry.callable_not_found",
                        tool=tool_name,
                        module=mod.__name__,
                    )
                    continue

                tool_map[tool_name] = func

                # Introspect signature for parameter schema
                sig = inspect.signature(func)
                full_doc = inspect.getdoc(func) or ""
                param_docs = _parse_docstring_args(full_doc)

                properties: dict[str, dict] = {}
                required: list[str] = []

                for param_name, param in sig.parameters.items():
                    if param_name == "context":
                        # Context is injected at runtime, not part of the LLM schema
                        continue

                    json_type = _python_type_to_json_schema(param.annotation)
                    description = param_docs.get(
                        param_name, f"The {param_name.replace('_', ' ')} value."
                    )

                    prop: dict[str, Any] = {
                        "type": json_type,
                        "description": description,
                    }

                    # Add default value hint when one exists
                    if param.default is not inspect.Parameter.empty:
                        prop["default"] = param.default

                    properties[param_name] = prop

                    if param.default is inspect.Parameter.empty:
                        required.append(param_name)

                # Use first line of docstring as the tool description
                desc = (full_doc.split("\n")[0].strip() if full_doc else f"Execute {tool_name}")

                tool_schemas.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "description": desc,
                            "parameters": {
                                "type": "object",
                                "properties": properties,
                                "required": required,
                            },
                        },
                    }
                )

        _TOOL_MAP = tool_map
        _TOOL_SCHEMAS = tool_schemas
        log.info("tool_registry.initialized", count=len(_TOOL_MAP))


def get_tool_schemas() -> list[dict]:
    """Get all registered tool schemas in OpenAI/Ollama format."""
    init_registry()
    return _TOOL_SCHEMAS


def get_tool_callable(tool_name: str) -> Callable | None:
    """Get the Python callable for a registered tool by name."""
    init_registry()
    return _TOOL_MAP.get(tool_name)
