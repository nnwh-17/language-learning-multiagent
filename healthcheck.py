"""Basic environment health check for the jp-anki-agent project.

Run from an empty folder:
    uv init --bare
    uv add pydantic-ai
    export ANTHROPIC_API_KEY=...        # or OPENAI_API_KEY / GEMINI_API_KEY
    uv run python healthcheck.py

Optionally pick a different model:
    HEALTHCHECK_MODEL=openai:gpt-5 uv run python healthcheck.py
"""

import os
import sys

DEFAULT_MODEL = "anthropic:claude-haiku-5-5"
KEY_VARS = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"]

try:
    from dotenv import load_dotenv
 
    load_dotenv()  # reads .env in the current folder into os.environ
except ImportError:
    pass

def ok(msg: str) -> None:
    print(f"[ OK ] {msg}")


def fail(msg: str) -> None:
    print(f"[FAIL] {msg}")


def main() -> int:
    failed = False

    # 1. Python version
    v = sys.version_info
    if v >= (3, 10):
        ok(f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        fail(f"Python {v.major}.{v.minor} found, need 3.10+")
        failed = True

    # 2. PydanticAI import
    try:
        import pydantic_ai
        from pydantic import BaseModel
        from pydantic_ai import Agent

        ok(f"pydantic-ai imported (version {getattr(pydantic_ai, '__version__', 'unknown')})")
    except ImportError as e:
        fail(f"Cannot import pydantic-ai: {e}  ->  run: uv add pydantic-ai")
        return 1

    # 3. MCP support (needed for the project requirement)
    try:
        from pydantic_ai.mcp import MCPToolset  # noqa: F401
 
        ok("MCP client support available (MCPToolset)")
    except ImportError as e:
        fail(f"MCP support missing: {e}  ->  run: pip install -U pydantic-ai")
        failed = True

    # 4. API key present
    found = [k for k in KEY_VARS if os.environ.get(k)]
    if found:
        ok(f"API key found: {', '.join(found)}")
    else:
        fail(f"No API key set. Export one of: {', '.join(KEY_VARS)}")
        return 1

    # 5. Live call with structured output (mirrors the future analyzer agent)
    model = os.environ.get("HEALTHCHECK_MODEL", DEFAULT_MODEL)

    class VocabItem(BaseModel):
        word: str
        reading: str
        meaning: str

    agent = Agent(
        model,
        output_type=VocabItem,
        system_prompt="Extract the single Japanese word from the text.",
    )

    try:
        result = agent.run_sync("猫")
        item = result.output
        ok(f"Live call to {model} worked -> {item.word} ({item.reading}): {item.meaning}")
    except Exception as e:  # noqa: BLE001
        fail(f"Live call to {model} failed: {type(e).__name__}: {e}")
        failed = True

    print()
    print("All checks passed." if not failed else "Some checks failed, see above.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())