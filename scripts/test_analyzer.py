"""Smoke-test tokenization, Japanese analysis, and orchestrator delegation.

The script prints each stage and verifies that both the analyzer and orchestrator use the
expected tools. Run with an optional Japanese sentence to try different input.
"""

import asyncio
import sys

from jplearn.agents.analyzer import analyzer
from jplearn.agents.orchestrator import orchestrator, tools_used
from jplearn.tokenizer import tokenize

# Windows consoles default to a code page that can't print Japanese.
sys.stdout.reconfigure(encoding="utf-8")

SENTENCE = sys.argv[1] if len(sys.argv) > 1 else "静かな部屋で日本語を勉強しなければならない。"


async def main() -> None:
    # First inspect deterministic tokenization, then validate the LLM-backed analysis.
    print("== tokenizer (no LLM)")
    for t in tokenize(SENTENCE):
        conj = f"  [{t.conjugation}]" if t.conjugation else ""
        print(f"  {t.surface}\t{t.reading}\t{t.lemma}({t.lemma_reading})\t{t.pos}{conj}")

    print("\n== analyzer agent")
    result = await analyzer.run(SENTENCE)
    b = result.output
    print(f"  {b.translation}")
    for w in b.words:
        print(f"  {w.surface} ({w.reading}) - {w.meaning}" + (f"  [{w.note}]" if w.note else ""))
    for g in b.grammar_points:
        print(f"  * {g.pattern}: {g.meaning}")
    assert "tokenize_japanese" in tools_used(result.all_messages()), "analyzer skipped the tokenizer"

    # Ensure a natural-language breakdown request is routed to the specialist agent.
    print("\n== orchestrator delegates to analyzer")
    result = await orchestrator.run(f"Can you break down this sentence? {SENTENCE}")
    tools = tools_used(result.all_messages())
    print(f"  tools used: {tools}")
    assert "analyze_japanese" in tools, "orchestrator did not call the analyzer"
    print(f"\n{result.output.reply}")


if __name__ == "__main__":
    asyncio.run(main())
