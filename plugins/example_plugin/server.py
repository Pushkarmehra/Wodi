"""
Example Woody MCP Plugin Server — demonstrates the plugin standard.

Tools:
  - get_joke: Returns a programming joke
  - get_quote: Returns an inspirational quote

This is a minimal example. Real plugins would call APIs, databases,
or system services within their declared permission scope.
"""
import json
import random
import sys

JOKES = [
    "Why do programmers prefer dark mode? Because light attracts bugs.",
    "A SQL query walks into a bar, walks up to two tables and asks... 'Can I join you?'",
    "Why do Java developers wear glasses? Because they don't C#.",
    "There are 10 types of people: those who understand binary and those who don't.",
]

QUOTES = [
    "The best way to predict the future is to invent it. — Alan Kay",
    "Any sufficiently advanced technology is indistinguishable from magic. — Arthur C. Clarke",
    "Move fast and build things. — Not Facebook",
    "Make it work, make it right, make it fast. — Kent Beck",
]


def get_joke() -> dict:
    return {"joke": random.choice(JOKES)}


def get_quote() -> dict:
    return {"quote": random.choice(QUOTES)}


def main() -> None:
    """Simple stdio MCP server — reads JSON requests, writes JSON responses."""
    for line in sys.stdin:
        try:
            request = json.loads(line.strip())
            tool = request.get("tool", "")
            if tool == "get_joke":
                result = get_joke()
            elif tool == "get_quote":
                result = get_quote()
            else:
                result = {"error": f"Unknown tool: {tool}"}
            print(json.dumps(result), flush=True)
        except Exception as e:
            print(json.dumps({"error": str(e)}), flush=True)


if __name__ == "__main__":
    main()
