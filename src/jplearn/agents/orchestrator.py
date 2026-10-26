"""Route user requests to Japanese-learning specialist agents and tools.

The chat frontends call this agent; it delegates to the analyzer, flashcard, example, and
research agents, while write operations pause for explicit user approval.
"""

from collections.abc import Callable

from pydantic import BaseModel, Field
from pydantic_ai import Agent, DeferredToolRequests, PartDeltaEvent, PartStartEvent, RunContext
from pydantic_ai.agent import EventStreamHandler
from pydantic_ai.messages import ModelMessage, ToolCallPart
from pydantic_core import from_json

from jplearn.activity import Observe, is_output_tool, track
from jplearn.agents.analyzer import Breakdown, analyzer
from jplearn.agents.examples import ExampleSet, examples_agent
from jplearn.agents.explainer import Explanation, explainer
from jplearn.agents.flashcards import (
    Card,
    CardDraft,
    Sentence,
    add_cards,
    add_examples,
    flashcard_agent,
)
from jplearn.agents.researcher import Material, researcher
from jplearn.config import DEFAULT_DECK, get_model
from jplearn.dictionary import DictEntry, lookup
from jplearn.user_context import use_user_context


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
2. Write a short plan of the steps you would take. The user sees it, so describe each step
   in plain words ("Look up 鳴る in the dictionary"), not tool names.
3. Carry out the plan and answer the user.

Specialists (tools):
- `analyze_japanese`: word-by-word breakdown of Japanese text (readings, dictionary
  forms, meanings, grammar points, translation). Use it whenever the user gives you
  Japanese text to understand, rather than analysing it yourself.
- `lookup_word`: JMdict dictionary entry for a single word. Use it for "what does X
  mean / how do you read X" questions, and base your answer on it.
- `explain_concept`: explains a grammar point, word, nuance or cultural idea with
  analogies, comparisons to related items, examples and common mistakes. Use it for
  "why / how does X work / what's the difference between X and Y / I don't get X"
  questions. Present its explanation conversationally; keep the analogy's limits and
  end with its check question.
- `draft_flashcards`: drafts NEW Anki cards for the words and grammar found in Japanese
  text (or a list of words). It does NOT add them. It breaks the text down itself, so don't
  call `analyze_japanese` first.
- `add_flashcards`: adds cards to Anki. The user is asked to approve before it runs, so
  call it straight after drafting (with the drafted cards unchanged) unless the user asked
  for changes; then apply their changes and call it again. If it is denied, do not retry.
- `generate_examples`: writes example sentences for one or more words (checked to really
  contain each word). Use it when the user wants more sentences/examples for words.
  Show each sentence with its translation and the form used.
- `add_examples_to_card`: puts example sentences ON the user's card for a word (or creates
  that one card if they have none). When the user asks to add example sentences to their
  card(s), use this with the sentences exactly as shown, NOT `draft_flashcards` (which
  would make cards for other words in the sentences). Needs approval, like `add_flashcards`.
- `find_material`: searches the web for Japanese reading material (articles, news, song
  pages, ...) and returns a passage plus its URL. Use it when the user asks you to find
  something to read. Always give the user the URL. If they then want a breakdown or
  flashcards, pass the returned passage to `analyze_japanese` / `draft_flashcards`.

For anything no specialist covers yet, answer directly.
When you write Japanese, add furigana for kanji the first time it appears, e.g. 食(た)べる.
Keep replies concise. Present breakdowns as a short table plus the grammar points.
After adding anything to Anki, report only what the tool result confirms (which card,
how many sentences or cards were added); never claim more.
"""

# The orchestrator returns either a user-facing plan/reply or deferred approval requests.
orchestrator = Agent(
    get_model(),
    output_type=[OrchestratorReply, DeferredToolRequests],
    instructions=INSTRUCTIONS,
    capabilities=[Observe("orchestrator")],
)
use_user_context(orchestrator, "orchestrator")


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
    with track("jmdict"):
        return lookup(word, reading)


@orchestrator.tool
async def explain_concept(ctx: RunContext, topic: str, request: str = "") -> Explanation:
    """Explain a Japanese concept with analogies and comparisons. `topic` is what to explain,
    e.g. 'は vs が' or '〜てしまう'; `request` holds the user's question or what confuses them."""
    prompt = f"Topic: {topic}" + (f"\nThe user asked: {request}" if request else "")
    result = await explainer.run(prompt, usage=ctx.usage)
    return result.output


@orchestrator.tool
async def draft_flashcards(ctx: RunContext, request: str) -> CardDraft:
    """Draft Anki flashcards. `request` is the Japanese text (or words) to make cards from,
    plus any wishes from the user such as deck name or 'grammar only'."""
    result = await flashcard_agent.run(request, usage=ctx.usage)
    return result.output


@orchestrator.tool
async def generate_examples(ctx: RunContext, words: list[str], request: str = "") -> ExampleSet:
    """Generate example sentences. `words` are the Japanese words (dictionary form);
    `request` holds wishes such as 'five each', 'casual speech' or 'about travel'."""
    prompt = f"Words: {', '.join(words)}" + (f"\nRequest: {request}" if request else "")
    result = await examples_agent.run(prompt, usage=ctx.usage)
    return result.output


@orchestrator.tool
async def find_material(ctx: RunContext, request: str) -> Material:
    """Find Japanese reading material on the web. `request` describes what the user wants,
    e.g. 'easy news article about cooking' or 'lyrics of 夜に駆ける by YOASOBI'."""
    result = await researcher.run(request, usage=ctx.usage)
    return result.output


@orchestrator.tool_plain(requires_approval=True)
async def add_examples_to_card(
    word: str, reading: str, meaning: str, sentences: list[Sentence], deck: str = DEFAULT_DECK
) -> dict:
    """Add example sentences to the user's existing Anki card for `word` (matched on the
    card's front, in any deck); sentences already on the card are skipped. If there is no
    card for `word`, one is created in `deck`. Requires the user's approval."""
    with track("anki_write"):
        return await add_examples(word, reading, meaning, sentences, deck)


@orchestrator.tool_plain(requires_approval=True)
async def add_flashcards(deck: str, cards: list[Card]) -> dict:
    """Add flashcards to the user's Anki deck. Requires the user's approval."""
    with track("anki_write"):
        return await add_cards(deck, cards)


def tools_used(messages: list[ModelMessage]) -> list[str]:
    """Names of the tools the orchestrator called, in order (excluding its final answer)."""
    return [
        p.tool_name
        for m in messages
        for p in m.parts
        if p.part_kind == "tool-call" and not is_output_tool(p.tool_name)
    ]


def stream_reply(on_reply: Callable[[str], None]) -> EventStreamHandler:
    """Event handler for `orchestrator.run(event_stream_handler=...)` that calls `on_reply`
    with the reply written so far, each time the model adds to it.

    The reply is structured output ({"plan": [...], "reply": "..."}), so it streams as JSON
    fragments: the output tool's arguments through LiteLLM, or the response text itself on
    the Claude API (native structured output). Partial parsing picks out the reply.
    """

    async def handle(ctx: RunContext, events) -> None:
        parts = {}  # part index -> the part so far, within the current model response
        async for event in events:
            if isinstance(event, PartStartEvent):
                parts[event.index] = event.part
            elif isinstance(event, PartDeltaEvent) and event.index in parts:
                parts[event.index] = event.delta.apply(parts[event.index])
            else:
                continue
            part = parts[event.index]
            if part.part_kind == "text":
                output = part.content
            elif part.part_kind == "tool-call" and is_output_tool(part.tool_name):
                output = part.args
            else:
                continue
            try:
                if not isinstance(output, dict):
                    output = from_json(output or "{}", allow_partial="trailing-strings")
            except ValueError:  # not JSON (e.g. a remark before a tool call), or cut off mid-token
                continue
            if isinstance(output, dict) and isinstance(reply := output.get("reply"), str):
                on_reply(reply)

    return handle


def describe_approval(call: ToolCallPart) -> str:
    """Markdown summary of a tool call waiting for the user's approval."""
    args = call.args_as_dict()
    # Present the pending Anki write in a form the user can review before approving.
    if call.tool_name == "add_examples_to_card":
        rows = "\n".join(f"| {s['japanese']} | {s['translation']} |" for s in args["sentences"])
        return (
            f"Add **{len(args['sentences'])} example sentences** to your **{args['word']}** card? "
            f"(If you don't have one, a card is created in **{args.get('deck', DEFAULT_DECK)}**.)\n\n"
            "| Japanese | Translation |\n|---|---|\n" + rows
        )
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
