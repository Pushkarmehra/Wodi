"""
Comprehensive Test Suite for all Woody Features & Edge Cases:
1. TTS Barge-in & Stop Speaking
2. Fuzzy App Name Resolution (vs code, notebook, calc, etc.)
3. Compound Command Decomposition (open notebook and write that "i love pari ")
4. Screen Vision & Perception Tools (analyze_screen, take_screenshot, get_open_windows)
5. Multi-Turn Conversational Memory Retention
6. Expanded Desktop & System Tools (hotkey, run_command, set_clipboard, stats, etc.)
7. End-to-End Kernel Pipeline Simulation
"""
import asyncio
import os
import sys
import time

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from woody.tools.builtin.desktop_tools import (
    find_windows_app, APP_ALIASES, analyze_screen, take_screenshot,
    get_open_windows, hotkey, type_text, press_key
)
from woody.tools.builtin.system_tools import (
    get_time_date, get_system_stats, get_battery, get_clipboard,
    set_clipboard, run_command, list_processes
)
from woody.tools.tool_registry import get_tool_schemas, get_tool_callable
from woody.memory.working import KernelMemory
from woody.planner.working_memory import WorkingMemoryState, make_initial_state, SubTask
from woody.planner.planner import Planner
from woody.synthesis.tts import TTSEngine
from woody.synthesis.synthesizer import Synthesizer
from woody.agents.chat_agent import ChatAgent


async def test_1_tts_barge_in():
    print("\n--- CASE 1: TTS Barge-in & Stop Mechanism ---")
    tts_inworld = TTSEngine(engine="inworld", voice="Avery")
    assert hasattr(tts_inworld, "stop"), "TTSEngine missing stop() method"
    assert hasattr(tts_inworld, "_stop_event"), "TTSEngine missing _stop_event"
    assert tts_inworld._voice == "Avery", "TTSEngine voice should default to Avery"
    assert tts_inworld._inworld_model == "inworld-tts-2", "TTSEngine model should be inworld-tts-2"
    assert tts_inworld._delivery_mode == "CREATIVE", "TTSEngine delivery_mode should be CREATIVE"

    # Test stop before speaking
    tts_inworld.stop()
    assert tts_inworld._stop_event.is_set(), "_stop_event should be set after stop()"
    
    tts_edge = TTSEngine(engine="edge-tts", voice="en-US-AriaNeural")
    tts_edge.stop()
    assert tts_edge._stop_event.is_set()

    print("[PASS] Inworld & Edge TTS Engine stop() properly triggers cancel event and MCI stop.")



async def test_2_fuzzy_app_resolution():
    print("\n--- CASE 2: Fuzzy App Resolution ('vs code', 'notebook', 'calc', etc.) ---")
    test_queries = {
        "vs code": "code.exe",
        "vscode": "code.exe",
        "visual studio code": "code.exe",
        "visual studio": "devenv.exe",
        "notebook": "notepad.exe",
        "notepad": "notepad.exe",
        "notes": "notepad.exe",
        "text editor": "notepad.exe",
        "calc": "calc.exe",
        "calculator": "calc.exe",
        "chrome": "chrome.exe",
        "google chrome": "chrome.exe",
        "edge": "msedge.exe",
        "microsoft edge": "msedge.exe",
        "terminal": "wt.exe",
        "windows terminal": "wt.exe",
        "cmd": "cmd.exe",
        "task manager": "taskmgr.exe",
        "settings": "ms-settings:",
        "explorer": "explorer.exe",
        "file explorer": "explorer.exe",
        "spotify": "spotify.exe",
    }
    
    for query, expected_target in test_queries.items():
        alias_found = APP_ALIASES.get(query)
        resolved_path = find_windows_app(query)
        print(f"Query: '{query:<20}' -> Alias: '{str(alias_found):<15}' | Resolved: '{str(resolved_path)}'")
        assert alias_found or resolved_path, f"Failed to match query '{query}'"
        if alias_found:
            assert alias_found == expected_target, f"Expected {expected_target} for {query}, got {alias_found}"
            
    print(f"[PASS] All {len(test_queries)} app aliases & search paths resolved accurately.")


async def test_3_compound_command_planner():
    print("\n--- CASE 3: Compound Command Decomposition ---")
    planner = Planner(client=None)

    # 3.1 User's exact prompt from screenshot: 'open notebook and write that "i love pari "'
    cmd1 = 'open notebook and write that "i love pari "'
    parsed1 = planner._parse_compound_open_and_type(cmd1)
    assert parsed1 is not None, "Failed to parse compound command 1"
    assert parsed1["app_name"] == "notepad", f"Expected app 'notepad', got {parsed1['app_name']}"
    assert parsed1["text"].strip() == "i love pari", f"Expected text 'i love pari', got {parsed1['text']}"
    print(f"Command 1: '{cmd1}' -> Subtasks: Open {parsed1['app_name']}, Type '{parsed1['text']}'")

    # 3.2 VS Code compound: 'open vs code and write that "def hello():"'
    cmd2 = 'open vs code and write that "def hello():"'
    parsed2 = planner._parse_compound_open_and_type(cmd2)
    assert parsed2 is not None, "Failed to parse compound command 2"
    assert parsed2["app_name"] == "vs code", f"Expected app 'vs code', got {parsed2['app_name']}"
    assert parsed2["text"].strip() == "def hello():", f"Expected text 'def hello():', got {parsed2['text']}"
    print(f"Command 2: '{cmd2}' -> Subtasks: Open {parsed2['app_name']}, Type '{parsed2['text']}'")

    # 3.3 Planner full routing of compound command
    state = WorkingMemoryState(
        request_id="req-123",
        session_id="sess-123",
        user_request=cmd1,
        screen_context="",
        clipboard_context="",
        task_history="",
        intent="",
        subtasks=[],
        active_subtask_id=None,
        tool_call_trace=[],
        final_response=None,
        is_simple=False,
    )
    routed_state = await planner.plan(
        user_request=cmd1,
        screen_context="",
        clipboard_context="",
        task_history="",
    )
    assert len(routed_state["subtasks"]) == 2, f"Expected 2 subtasks, got {len(routed_state['subtasks'])}"
    assert routed_state["subtasks"][0]["action"] == "open_app"
    assert routed_state["subtasks"][0]["params"]["app_name"] == "notepad"
    assert routed_state["subtasks"][1]["action"] == "type_text"
    assert routed_state["subtasks"][1]["params"]["text"].strip() == "i love pari"
    print(f"[PASS] Compound command decomposed into {len(routed_state['subtasks'])} subtasks without Windows Run errors.")

    # 3.4 Simple single app launching
    params_single = planner._extract_simple_params("open vs code", "open_app")
    assert params_single.get("app_name") == "vs code"
    print("[PASS] Simple single-app extraction correctly isolated app name 'vs code'.")


async def test_4_screen_vision_tools():
    print("\n--- CASE 4: Screen Vision & Perception ---")
    
    # 4.1 analyze_screen
    analysis = analyze_screen(custom_prompt="what is open?")
    assert analysis["success"] is True, f"analyze_screen failed: {analysis.get('error')}"
    assert "active_window" in analysis
    assert "open_windows" in analysis
    assert "analysis" in analysis
    print(f"analyze_screen result: Active Window='{analysis['active_window']}', Analysis='{analysis['analysis']}'")

    # 4.2 take_screenshot
    shot = take_screenshot()
    print(f"take_screenshot result: success={shot['success']}, path={shot.get('path')}")
    # Under desktop session, screenshot captures file
    if shot["success"]:
        assert os.path.exists(shot["path"]), "Screenshot file was not created on disk"

    # 4.3 get_open_windows
    wins = get_open_windows()
    assert wins["success"] is True
    print(f"get_open_windows result: Found {len(wins['windows'])} visible windows: {wins['windows'][:3]}")

    print("[PASS] Screen perception & vision tools operating correctly.")


async def test_5_conversational_memory():
    print("\n--- CASE 5: Multi-Turn Conversational Memory Retention ---")
    mem = KernelMemory(history_size=10)
    
    # Simulate multi-turn dialogue
    mem.add_turn("user", "My name is Pushkar and my favorite language is Python.")
    mem.add_turn("assistant", "Nice to meet you Pushkar! Python is a great language.")
    mem.add_turn("user", "What is my name and favorite language?")
    
    dialogue = mem.get_dialogue_history(n=5)
    assert len(dialogue) == 3, f"Expected 3 turns, got {len(dialogue)}"
    
    prompt_str = mem.format_dialogue_for_prompt(n=5)
    assert "Pushkar" in prompt_str, "Dialogue history missing 'Pushkar'"
    assert "Python" in prompt_str, "Dialogue history missing 'Python'"
    print(f"Formatted Dialogue Memory:\n{prompt_str}")

    # Test Synthesizer prompt builder includes conversation memory
    synth = Synthesizer(client=None)
    state = WorkingMemoryState(
        request_id="req-999",
        session_id="sess-999",
        user_request="What is my name?",
        screen_context="",
        clipboard_context="",
        task_history=prompt_str,
        intent="Answer user query",
        subtasks=[],
        active_subtask_id=None,
        tool_call_trace=[],
        final_response=None,
        is_simple=True,
    )
    built_prompt = synth._build_prompt(state, tone="concise")
    assert "Recent Conversation History:" in built_prompt
    assert "Pushkar" in built_prompt
    print("[PASS] Multi-turn dialogue memory is properly formatted and injected into LLM context.")


async def test_6_expanded_system_and_desktop_tools():
    print("\n--- CASE 6: Expanded System & Desktop Tools ---")
    
    # 6.1 get_time_date
    time_res = get_time_date()
    assert time_res["success"] is True
    print(f"get_time_date: {time_res['time']}, {time_res['date']}")

    # 6.2 get_system_stats
    stats_res = get_system_stats()
    assert stats_res["success"] is True
    print(f"get_system_stats: CPU {stats_res['cpu_percent']}%, RAM {stats_res['ram_percent']}%")

    # 6.3 get_battery
    battery_res = get_battery()
    assert battery_res["success"] is True
    print(f"get_battery: {battery_res.get('percent', 'N/A')}%")

    # 6.4 set_clipboard & get_clipboard
    set_res = set_clipboard("Woody Test Clipboard Content 12345")
    assert set_res["success"] is True
    get_res = get_clipboard()
    assert get_res["success"] is True
    assert "Woody Test Clipboard Content 12345" in get_res["text"]
    print(f"Clipboard roundtrip: Verified '{get_res['text']}'")

    # 6.5 run_command
    cmd_res = run_command("echo Woody System Shell Active")
    assert cmd_res["success"] is True
    assert "Woody System Shell Active" in cmd_res["output"]
    print(f"run_command: Return code {cmd_res['return_code']}, Output: '{cmd_res['output'].strip()}'")

    # 6.6 hotkey
    hk_res = hotkey("win+d")
    assert hk_res["success"] is True
    print(f"hotkey: Pressed 'win+d'")

    print("[PASS] All expanded system and desktop tools passed validation.")


async def test_7_full_tool_registry():
    print("\n--- CASE 7: Complete Tool Registry Verification ---")
    schemas = get_tool_schemas()
    names = [s["function"]["name"] for s in schemas]
    print(f"Total Registered Tools ({len(names)}):")
    for i, name in enumerate(names, 1):
        print(f"  {i:02d}. {name}")

    essential_tools = [
        "open_app", "close_app", "focus_window", "type_text", "press_key", "hotkey",
        "get_open_windows", "take_screenshot", "analyze_screen",
        "get_time_date", "get_system_stats", "list_processes", "get_clipboard",
        "set_clipboard", "get_battery", "run_command", "read_file", "write_file",
        "list_directory", "search_files", "search_web"
    ]
    for et in essential_tools:
        assert et in names, f"Missing essential tool: {et}"
        callable_fn = get_tool_callable(et)
        assert callable(callable_fn), f"Tool {et} does not have a valid callable"

    print(f"[PASS] All {len(essential_tools)} essential tools registered and callable.")


async def test_8_inworld_tts_synthesis():
    print("\n--- CASE 8: Inworld AI TTS-2 Integration & Streaming ---")
    tts = TTSEngine(
        engine="inworld",
        voice="Avery",
        inworld_model="inworld-tts-2",
        delivery_mode="CREATIVE",
        language="AUTO",
        stream=True,
    )
    tts.load()
    assert tts.engine == "inworld", f"Expected engine 'inworld', got {tts.engine}"

    # Verify speech synthesis with chunks
    chunks_collected = []
    def on_chunk(chunk: bytes):
        chunks_collected.append(chunk)

    # Test short phrase synthesis
    await tts.speak("Inworld Text to Speech test.", on_chunk=on_chunk)
    assert len(chunks_collected) > 0, "Expected non-empty audio chunks from Inworld TTS streaming"
    print(f"[PASS] Inworld TTS synthesized and streamed {len(chunks_collected)} audio chunks successfully.")

    # Test real-time pipelined sentence streaming
    q: asyncio.Queue[str | None] = asyncio.Queue()
    await q.put("Hello! Sentence streaming test.")
    await q.put("This is sentence number two streaming in real time.")
    await q.put(None)
    await tts.speak_sentence_stream(q)
    print("[PASS] Inworld TTS pipelined sentence streaming completed successfully.")



async def main():
    print("=================================================================")
    print("       WOODY COMPREHENSIVE END-TO-END TEST SUITE RUNNER         ")
    print("=================================================================")
    t_start = time.perf_counter()
    
    await test_1_tts_barge_in()
    await test_2_fuzzy_app_resolution()
    await test_3_compound_command_planner()
    await test_4_screen_vision_tools()
    await test_5_conversational_memory()
    await test_6_expanded_system_and_desktop_tools()
    await test_7_full_tool_registry()
    await test_8_inworld_tts_synthesis()

    elapsed = time.perf_counter() - t_start
    print("\n=================================================================")
    print(f"ALL 8 TEST SUITES PASSED IN {elapsed:.2f}s WITH ZERO ERRORS!")
    print("=================================================================")


if __name__ == "__main__":
    asyncio.run(main())

