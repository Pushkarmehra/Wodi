"""
Verification script for Woody enhancements:
- App alias resolution (vs code, notebook, calc, etc.)
- Compound command planner (open notebook and write that "i love pari ")
- Memory and dialogue history tracking
- Screen analysis and desktop tools
"""
import asyncio
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from woody.tools.builtin.desktop_tools import find_windows_app, APP_ALIASES, analyze_screen, hotkey
from woody.tools.tool_registry import get_tool_schemas, get_tool_callable
from woody.memory.working import KernelMemory
from woody.planner.planner import Planner


async def run_tests():
    print("=== 1. Testing App Resolution & Aliases ===")
    test_apps = ["vs code", "vscode", "visual studio code", "notebook", "notepad", "calculator", "calc", "chrome"]
    for app in test_apps:
        res = find_windows_app(app)
        alias = APP_ALIASES.get(app)
        print(f"App: '{app}' -> alias: '{alias}', resolved path: '{res}'")
        assert alias or res, f"Failed to find or resolve alias for '{app}'"
    print("[OK] App alias & resolution test passed!")

    print("\n=== 2. Testing Tool Registry ===")
    schemas = get_tool_schemas()
    tool_names = [s["function"]["name"] for s in schemas]
    print(f"Registered {len(schemas)} tools: {', '.join(tool_names)}")
    assert "analyze_screen" in tool_names
    assert "open_app" in tool_names
    assert "type_text" in tool_names
    assert "press_key" in tool_names
    assert "hotkey" in tool_names
    assert "run_command" in tool_names
    assert "set_clipboard" in tool_names
    print("[OK] Tool registry contains all new and updated tools!")

    print("\n=== 3. Testing Compound Command Parsing in Planner ===")
    planner = Planner(client=None)

    # Test compound command
    compound_cmd = 'open notebook and write that "i love pari "'
    parsed = planner._parse_compound_open_and_type(compound_cmd)
    print(f"Command: '{compound_cmd}' -> Parsed: {parsed}")
    assert parsed is not None
    assert parsed["app_name"] == "notepad"
    assert parsed["text"].strip() == "i love pari"

    # Test single app extraction
    params_vs = planner._extract_simple_params("open vs code", "open_app")
    print(f"Command: 'open vs code' -> Params: {params_vs}")
    assert params_vs.get("app_name") == "vs code"

    params_nb = planner._extract_simple_params("open notebook", "open_app")
    print(f"Command: 'open notebook' -> Params: {params_nb}")
    assert params_nb.get("app_name") == "notepad"
    print("[OK] Compound command and app extraction test passed!")

    print("\n=== 4. Testing Multi-Turn Dialogue Memory ===")
    mem = KernelMemory()
    mem.add_turn("user", "Hello Woody, my favorite color is emerald green.")
    mem.add_turn("assistant", "Hello! Emerald green is a fantastic color.")
    mem.add_turn("user", "What is my favorite color?")
    history_str = mem.format_dialogue_for_prompt(n=4)
    print(f"Dialogue Memory:\n{history_str}")
    assert "emerald green" in history_str
    print("[OK] Dialogue memory retention test passed!")

    print("\n=== 5. Testing Screen Analysis Tool ===")
    analysis = analyze_screen()
    print(f"Screen analysis result: success={analysis.get('success')}, window='{analysis.get('active_window')}', text_len={len(analysis.get('visible_text', ''))}")
    assert analysis.get("success") is True
    print("[OK] Screen analysis tool test passed!")

    print("\n==============================================")
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("==============================================")


if __name__ == "__main__":
    asyncio.run(run_tests())
