from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelMessage

from jplearn.agents.analyzer import Breakdown, analyzer
from jplearn.config import get_model
from jplearn.dictionary import DictEntry, lookup


class OrchestratorReply(BaseModel):
    plan: list[str] = Field(
        description="Short step-by-step plan for handling the request. Empty for small talk."
    )
    reply: str = Field(description="The message shown to the user.")


INSTRUCTIONS = """\
You are the orchestrator of a Japanese-learning assistant. The user is an English
speaker learning Japanese.

For every message:
1. Work out what the user wants (explain grammar, break down a sentence, quiz them,
   make flashcards, find material, casual practice, ...).
2. Write a short plan of the steps you would take, naming the specialist you will use.
3. Carry out the plan and answer the user.

Specialists (tools):
- `analyze_japanese`: word-by-word breakdown of Japanese text (readings, dictionary
  forms, meanings, grammar points, translation). Use it whenever the user gives you
  Japanese text to understand, rather than analysing it yourself.
- `lookup_word`: JMdict dictionary entry for a single word. Use it for "what does X
  mean / how do you read X" questions, and base your answer on it.

For anything no specialist covers yet, answer directly.
When you write Japanese, add furigana for kanji the first time it appears, e.g. 食(た)べる.
Keep replies concise. Present breakdowns as a short table plus the grammar points.
"""

orchestrator = Agent(
    get_model(),
    output_type=OrchestratorReply,
    instructions=INSTRUCTIONS,
)


@orchestrator.tool
async def analyze_japanese(ctx: RunContext, text: str) -> Breakdown:
    """Break down Japanese text: translation, each word's reading, dictionary form and
    meaning, and the grammar points used. Pass the Japanese text only."""
    result = await analyzer.run(text, usage=ctx.usage)
    return result.output


@orchestrator.tool_plain
def lookup_word(word: str, reading: str | None = None) -> list[DictEntry]:
    """Look up a Japanese word in JMdict. `word` is the dictionary form in kanji or kana;
    `reading` (hiragana) optionally narrows homographs. Returns up to 3 entries."""
    return lookup(word, reading)


def tools_used(messages: list[ModelMessage]) -> list[str]:
    """Names of the tools the orchestrator called, in order (excluding its final answer)."""
    return [
        p.tool_name
        for m in messages
        for p in m.parts
        if p.part_kind == "tool-call" and not p.tool_name.startswith("final_result")
    ]
