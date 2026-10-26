"""Check project dependencies and integration points before running jplearn.

The checks cover PydanticAI, model configuration, SudachiPy, JMdict, and the UI's agent
diagram; ``--live`` additionally sends a small request through the configured model.
"""

import asyncio
import os
import sys
import traceback

from dotenv import load_dotenv

# Windows consoles default to a code page that can't print Japanese.
sys.stdout.reconfigure(encoding="utf-8")

# Read the same local environment configuration used by the app.
load_dotenv()

results: list[tuple[str, bool, str]] = []


# Collect each check independently so one failure does not hide later results.
def check(name):
    def wrap(fn):
        try:
            detail = fn()
            results.append((name, True, detail or ""))
        except Exception as e:
            results.append((name, False, f"{type(e).__name__}: {e}"))
            if "-v" in sys.argv:
                traceback.print_exc()
        return fn

    return wrap


@check("pydantic-ai import")
def _():
    import pydantic_ai

    return pydantic_ai.__version__


@check("pydantic-ai MCP support")
def _():
    from pydantic_ai.mcp import MCPToolset  # noqa: F401


@check("model settings in .env")
def _():
    from jplearn.config import MODEL_NAME, PROVIDER, get_model

    get_model()  # raises on an unknown JPLEARN_PROVIDER
    if PROVIDER == "anthropic":
        if os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"):
            return f"Claude API, {MODEL_NAME}"
        return f"Claude API, {MODEL_NAME} (no ANTHROPIC_API_KEY; relying on an `ant auth login` profile)"
    missing = [k for k in ("LITELLM_API_BASE", "LITELLM_API_KEY") if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"missing {', '.join(missing)} - copy .env.example to .env")
    return f"LiteLLM at {os.getenv('LITELLM_API_BASE')}, {MODEL_NAME}"


@check("sudachi tokenizer")
def _():
    from sudachipy import Dictionary, SplitMode

    tokenizer = Dictionary().tokenizer()
    tokens = tokenizer.tokenize("昨日、友達と映画を見に行きました。", SplitMode.C)
    words = [(m.surface(), m.dictionary_form(), m.reading_form(), m.part_of_speech()[0]) for m in tokens]
    assert any(w[1] == "行く" for w in words), words
    return " ".join(w[0] for w in words)


@check("JMdict dictionary")
def _():
    from jplearn.dictionary import lookup

    entries = lookup("食べる")
    assert entries and "to eat" in entries[0].senses[0].meanings, entries
    return "食べる -> to eat"


@check("architecture diagram matches agents")
def _():
    from jplearn.architecture import check_against_agents

    if problems := check_against_agents():
        raise RuntimeError("; ".join(problems) + " - update src/jplearn/architecture.py")


# Make the external model call opt-in because it uses the configured service.
if "--live" in sys.argv:

    @check("LLM round trip")
    def _():
        from pydantic_ai import Agent

        from jplearn.config import MODEL_NAME, get_model

        agent = Agent(get_model())
        out = asyncio.run(agent.run("Reply with only the word: こんにちは")).output
        return f"{MODEL_NAME} -> {out.strip()}"


# Print a compact report and return a failing process status if any check failed.
width = max(len(name) for name, _, _ in results)
for name, ok, detail in results:
    print(f"[{'OK' if ok else 'FAIL'}] {name.ljust(width)}  {detail}")

sys.exit(0 if all(ok for _, ok, _ in results) else 1)
