"""Checks that the dependencies we rely on work. Run: python scripts/healthcheck.py [--live]

--live also sends one tiny request to the LLM (costs a few tokens).
"""

import asyncio
import os
import sys
import traceback

from dotenv import load_dotenv

load_dotenv()

results: list[tuple[str, bool, str]] = []


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


@check("LiteLLM settings in .env")
def _():
    missing = [k for k in ("LITELLM_API_BASE", "LITELLM_API_KEY") if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"missing {', '.join(missing)} - copy .env.example to .env")
    return os.getenv("LITELLM_API_BASE")


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


if "--live" in sys.argv:

    @check("LLM round trip")
    def _():
        from pydantic_ai import Agent

        from jplearn.config import MODEL_NAME, get_model

        agent = Agent(get_model())
        out = asyncio.run(agent.run("Reply with only the word: こんにちは")).output
        return f"{MODEL_NAME} -> {out.strip()}"


width = max(len(name) for name, _, _ in results)
for name, ok, detail in results:
    print(f"[{'OK' if ok else 'FAIL'}] {name.ljust(width)}  {detail}")

sys.exit(0 if all(ok for _, ok, _ in results) else 1)
