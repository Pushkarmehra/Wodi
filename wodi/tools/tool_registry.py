"""
Tool Registry — Dynamically generates OpenAI-compatible tool schemas for built-in tools.
"""
from __future__ import annotations

import inspect
from typing import Any, Callable

from wodi.tools.builtin import browser_tools, desktop_tools, filesystem_tools, system_tools
from wodi.utils.logging import get_logger

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

def _python_type_to_json_schema(py_type: Any) -> str:
    """Map Python types to JSON schema types."""
    if py_type == str or getattr(py_type, "__name__", "") == "str":
        return "string"
    if py_type == int or getattr(py_type, "__name__", "") == "int":
        return "integer"
    if py_type == float or getattr(py_type, "__name__", "") == "float":
        return "number"
    if py_type == bool or getattr(py_type, "__name__", "") == "bool":
        return "boolean"
    if py_type == dict or getattr(py_type, "__name__", "") == "dict":
        return "object"
    if py_type == list or getattr(py_type, "__name__", "") == "list":
        return "array"
    return "string"  # Default fallback

def init_registry() -> None:
    """Initialize the registry by introspecting built-in tools."""
    global _TOOL_MAP, _TOOL_SCHEMAS
    if _TOOL_MAP:
        return  # Already initialized

    for mod in BUILTIN_MODULES:
        if not hasattr(mod, "TOOLS"):
            continue
            
        for tool_name in mod.TOOLS:
            func = getattr(mod, tool_name, None)
            if not func or not callable(func):
                continue
                
            _TOOL_MAP[tool_name] = func
            
            # Introspect signature
            sig = inspect.signature(func)
            properties = {}
            required = []
            
            for param_name, param in sig.parameters.items():
                if param_name == "context": # skip context injection
                    continue
                param_type = _python_type_to_json_schema(param.annotation)
                properties[param_name] = {
                    "type": param_type,
                    "description": f"Parameter {param_name}",
                }
                if param.default == inspect.Parameter.empty:
                    required.append(param_name)
                    
            # Parse docstring for description
            doc = inspect.getdoc(func) or f"Execute {tool_name}"
            desc = doc.split("\n")[0] # Use first line
            
            _TOOL_SCHEMAS.append({
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": desc,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    }
                }
            })
            
    log.info("tool_registry.initialized", count=len(_TOOL_MAP))

def get_tool_schemas() -> list[dict]:
    """Get all tool schemas in OpenAI format."""
    init_registry()
    return _TOOL_SCHEMAS

def get_tool_callable(tool_name: str) -> Callable | None:
    """Get the python function for a tool."""
    init_registry()
    return _TOOL_MAP.get(tool_name)
