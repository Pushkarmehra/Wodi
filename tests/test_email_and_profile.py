"""
Unit tests for email drafting and persistent user profile tools in Woody.
"""
import asyncio
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from woody.tools.builtin.desktop_tools import compose_email, get_user_profile, set_user_profile
from woody.tools.tool_registry import get_tool_schemas, get_tool_callable
from woody.agents.desktop_agent import DesktopAgent
from woody.memory.semantic import SemanticMemory


async def test_email_and_profile():
    print("=== 1. Testing User Profile Get / Set in Semantic Memory ===")
    res_set = set_user_profile(name="Pushkar", tone="concise", preferred_email_app="gmail")
    assert res_set["success"] is True
    assert res_set["name"] == "Pushkar"

    res_get = get_user_profile()
    assert res_get["success"] is True
    assert res_get["name"] == "Pushkar"
    assert res_get["preferred_email_app"] == "gmail"
    print(f"[OK] Profile saved and verified: {res_get}")

    print("\n=== 2. Testing Tool Registry Introspection ===")
    schemas = get_tool_schemas()
    tool_names = [s["function"]["name"] for s in schemas]
    print(f"Registered tools: {', '.join(tool_names)}")
    assert "compose_email" in tool_names
    assert "get_user_profile" in tool_names
    assert "set_user_profile" in tool_names
    print("[OK] compose_email, get_user_profile, and set_user_profile present in tool registry schemas!")

    print("\n=== 3. Testing DesktopAgent Email & Profile Actions ===")
    agent = DesktopAgent()

    profile_result = await agent.execute_action("get_user_profile", {}, {})
    assert profile_result.success is True
    assert profile_result.output["name"] == "Pushkar"
    print(f"[OK] DesktopAgent get_user_profile output: {profile_result.output}")

    print("\n==============================================")
    print("EMAIL & PROFILE TESTS COMPLETED SUCCESSFULLY!")
    print("==============================================")


if __name__ == "__main__":
    asyncio.run(test_email_and_profile())
