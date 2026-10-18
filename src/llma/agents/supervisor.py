import os
from pathlib import Path
 
from pydantic_ai import Agent, RunContext
 
from llma.agents.analyzer import DEFAULT_MODEL, analyzer_agent
from llma.agents.example_generator import generate_all
from llma.deps import State
from llma.services.deck_builder import build_deck as write_deck
 
SYSTEM_PROMPT = """You are llma, a friendly assistant that helps people learn Japanese.
You coordinate specialist tools; do not do their work yourself.
 
Tools:
- analyze_text: extract vocab and grammar from Japanese text.
- generate_examples: write new example sentences for the analyzed items.
- build_deck: write the Anki import file.
 
Rules:
- If the user wants cards but gave no Japanese text, ask them to paste some.
- Typical order: analyze_text, then generate_examples, then build_deck.
- Only run steps the user asked for. Offer the next step instead of assuming it.
- Never invent vocab or readings. Use tool results.
- Web search, quizzes and mistake tracking are not available yet; say so if asked.
- Keep replies short."""
 
 
# --- Tools: each one hands a task to a specialist. Results go into ctx.deps (State). ---
 
 
async def analyze_text(ctx: RunContext[State], text: str) -> str:
    """Extract vocab and grammar from Japanese text. Replaces any earlier analysis.
 
    Args:
        text: The Japanese text to analyze.
    """
    # usage=ctx.usage adds the worker's tokens to the supervisor's total
    result = await analyzer_agent.run(text, usage=ctx.usage)
    a = result.output
 
    ctx.deps.analysis = a
    ctx.deps.examples = {}  # old examples belong to the old analysis
 
    vocab = "\n".join(f"- {v.word} ({v.reading}): {v.meaning}" for v in a.vocab)
    grammar = "\n".join(f"- {g.pattern}: {g.explanation}" for g in a.grammar)
    return f"Vocab ({len(a.vocab)}):\n{vocab}\n\nGrammar ({len(a.grammar)}):\n{grammar}"
 
 
async def generate_examples(ctx: RunContext[State], per_item: int = 2) -> str:
    """Write new example sentences for every analyzed vocab item and grammar point.
 
    Args:
        per_item: Sentences per item (1 to 3).
    """
    if ctx.deps.analysis is None:
        return "Nothing analyzed yet. Ask the user for Japanese text first."
 
    per_item = max(1, min(per_item, 3))
    ctx.deps.examples = await generate_all(ctx.deps.analysis, n=per_item)
    return f"Generated examples for {len(ctx.deps.examples)} items."
 
 
async def build_deck(ctx: RunContext[State], filename: str = "deck.txt") -> str:
    """Write the Anki import file from the analysis (and examples, if generated).
 
    Args:
        filename: Output file name, saved inside the output folder.
    """
    if ctx.deps.analysis is None:
        return "Nothing analyzed yet. Ask the user for Japanese text first."
 
    # .name strips any folders, so the file always stays in output/
    path =(Path(filename).name or "deck.txt")
    path, count = write_deck(ctx.deps.analysis, ctx.deps.examples, path)
 
    note = "" if ctx.deps.examples else " (no example sentences yet)"
    return f"Saved {count} cards to {path}{note}. In Anki: File > Import."
 
 
def build_supervisor(toolsets: list | None = None) -> Agent[State, str]:
    """toolsets is where MCP servers plug in later (see chat.py)."""
    return Agent(
        os.environ.get("JP_ANKI_MODEL", DEFAULT_MODEL),
        deps_type=State,
        system_prompt=SYSTEM_PROMPT,
        tools=[analyze_text, generate_examples, build_deck],
        toolsets=toolsets,
    )
 