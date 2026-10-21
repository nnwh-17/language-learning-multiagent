from pydantic import BaseModel, Field
from pydantic_ai import Agent, DeferredToolRequests, RunContext
from pydantic_ai.messages import ModelMessage, ToolCallPart

from jplearn.agents.analyzer import Breakdown, analyzer
from jplearn.agents.flashcards import Card, CardDraft, add_cards, flashcard_agent
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
- `draft_flashcards`: drafts Anki cards from Japanese text (or a list of words). It does
  NOT add them. It breaks the text down itself, so don't call `analyze_japanese` first.
- `add_flashcards`: adds cards to Anki. The user is asked to approve before it runs, so
  call it straight after drafting (with the drafted cards unchanged) unless the user asked
  for changes; then apply their changes and call it again. If it is denied, do not retry.

For anything no specialist covers yet, answer directly.
When you write Japanese, add furigana for kanji the first time it appears, e.g. 食(た)べる.
Keep replies concise. Present breakdowns as a short table plus the grammar points.
"""

orchestrator = Agent(
    get_model(),
    output_type=[OrchestratorReply, DeferredToolRequests],
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


@orchestrator.tool
async def draft_flashcards(ctx: RunContext, request: str) -> CardDraft:
    """Draft Anki flashcards. `request` is the Japanese text (or words) to make cards from,
    plus any wishes from the user such as deck name or 'grammar only'."""
    result = await flashcard_agent.run(request, usage=ctx.usage)
    return result.output


@orchestrator.tool_plain(requires_approval=True)
async def add_flashcards(deck: str, cards: list[Card]) -> dict:
    """Add flashcards to the user's Anki deck. Requires the user's approval."""
    return await add_cards(deck, cards)


def tools_used(messages: list[ModelMessage]) -> list[str]:
    """Names of the tools the orchestrator called, in order (excluding its final answer)."""
    return [
        p.tool_name
        for m in messages
        for p in m.parts
        if p.part_kind == "tool-call" and not p.tool_name.startswith("final_result")
    ]


def describe_approval(call: ToolCallPart) -> str:
    """Markdown summary of a tool call waiting for the user's approval."""
    args = call.args_as_dict()
    if call.tool_name != "add_flashcards":
        return f"`{call.tool_name}` with {args}"
    cards = [Card.model_validate(c) for c in args["cards"]]
    rows = "\n".join(
        f"| {c.kind} | {c.front} | {c.reading} | {c.meaning} | {c.example} |" for c in cards
    )
    return (
        f"Add **{len(cards)} cards** to deck **{args['deck']}**?\n\n"
        "| Type | Front | Reading | Meaning | Example |\n|---|---|---|---|---|\n" + rows
    )
