import asyncio
import os
 
from pydantic_ai import Agent
 
from llma.agents.analyzer import DEFAULT_MODEL
from llma.models.analysis import AnalysisResult, GrammarPoint, VocabItem
from llma.models.examples import ExampleSentence, GeneratedExamples
 
SYSTEM_PROMPT = """You write example sentences for Japanese learners.
 
- Use the target word or grammar pattern exactly, in a natural everyday context.
- Keep sentences short and at beginner level (N5-N4) unless told otherwise.
- Use vocabulary a beginner already knows; avoid rare words and kanji.
- Make each sentence different in situation, not just a word swap.
- Give a full hiragana reading and a natural English translation."""
 
# Same env var as the analyzer, so one setting controls both agents
example_agent = Agent(
    os.environ.get("JP_ANKI_MODEL", DEFAULT_MODEL),
    output_type=GeneratedExamples,
    system_prompt=SYSTEM_PROMPT,
)
 
 
def _vocab_prompt(v: VocabItem, n: int) -> str:
    return f"Write {n} example sentences for the word: {v.word} ({v.reading}) - {v.meaning}"
 
 
def _grammar_prompt(g: GrammarPoint, n: int) -> str:
    return f"Write {n} example sentences for the grammar pattern: {g.pattern} - {g.explanation}"
 
 
async def generate_all(
    analysis: AnalysisResult, n: int = 2, max_concurrent: int = 5
) -> dict[str, list[ExampleSentence]]:
    """One agent call per item, run in parallel. Returns {word or pattern: examples}."""
    # Semaphore caps simultaneous calls to avoid rate limits
    sem = asyncio.Semaphore(max_concurrent)
 
    async def run(key: str, prompt: str) -> tuple[str, list[ExampleSentence]]:
        async with sem:
            result = await example_agent.run(prompt)
        return key, result.output.examples
 
    jobs = [run(v.word, _vocab_prompt(v, n)) for v in analysis.vocab]
    jobs += [run(g.pattern, _grammar_prompt(g, n)) for g in analysis.grammar]
 
    # gather runs all jobs concurrently and keeps the order
    return dict(await asyncio.gather(*jobs))