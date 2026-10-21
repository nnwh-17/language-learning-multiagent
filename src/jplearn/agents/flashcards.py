import html
import os
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from jplearn.activity import Observe, track
from jplearn.agents.analyzer import Breakdown, analyzer
from jplearn.anki import anki_toolset, flashcard_toolset
from jplearn.config import get_model
from jplearn.user_context import use_user_context

DEFAULT_DECK = os.getenv("JPLEARN_DECK", "jplearn")
NOTE_TYPE = "Basic"  # fields: Front, Back


class Card(BaseModel):
    kind: Literal["vocab", "grammar"]
    front: str = Field(description="Dictionary form of the word, or the grammar pattern (e.g. 〜なければならない)")
    reading: str = Field(description="Hiragana reading (for grammar: empty string)")
    meaning: str = Field(description="Concise English meaning")
    example: str = Field(description="Japanese example sentence, preferably from the source text")
    example_translation: str
    notes: str | None = Field(default=None, description="Short usage note, e.g. intransitive pair")


class CardDraft(BaseModel):
    deck: str
    cards: list[Card]
    skipped: list[str] = Field(
        default=[], description="Words left out and why, e.g. '食べる (already in Anki)'"
    )


INSTRUCTIONS = f"""\
You make Anki flashcards for an English-speaking learner of Japanese.

1. Call `break_down` on the user's Japanese text to get dictionary-checked words and grammar.
2. Pick the words and grammar points worth studying. Skip particles, punctuation, names and
   very basic words (です, する, これ) unless the user asks for everything.
3. Check what is already in Anki with `findNotes`, searching all candidates at once, e.g.
   `"front:食べる" OR "front:勉強"`. Leave out existing ones and list them in `skipped`.
4. Return the cards. `front` is the dictionary form (or grammar pattern), the example should
   come from the source text when possible. Use the deck the user asked for, else "{DEFAULT_DECK}".

You only draft cards; you cannot add them.
"""


async def track_anki_read(ctx, call_tool, name, args):
    """Mark the read-only Anki MCP as running while one of its tools is called."""
    with track("anki_read"):
        return await call_tool(name, args)


flashcard_agent = Agent(
    get_model(),
    output_type=CardDraft,
    instructions=INSTRUCTIONS,
    capabilities=[Observe("flashcards")],
    toolsets=[
        flashcard_toolset(read_only=True, tools={"findNotes"}, process_tool_call=track_anki_read)
    ],
)
use_user_context(flashcard_agent, "flashcards")


@flashcard_agent.tool
async def break_down(ctx: RunContext, text: str) -> Breakdown:
    """Break Japanese text into words (with JMdict meanings) and grammar points."""
    result = await analyzer.run(text, usage=ctx.usage)
    return result.output


def card_fields(card: Card) -> dict[str, str]:
    """Anki Basic note fields for a card."""
    e = html.escape
    back = [f"<b>{e(card.reading)}</b>" if card.reading else "", e(card.meaning), ""]
    back += [e(card.example), f"<i>{e(card.example_translation)}</i>"]
    if card.notes:
        back += ["", f"<small>{e(card.notes)}</small>"]
    return {"Front": e(card.front), "Back": "<br>".join(back).removeprefix("<br>")}


class Sentence(BaseModel):
    japanese: str
    translation: str


def sentences_html(sentences: list[Sentence]) -> str:
    e = html.escape
    return "<br><br>".join(f"{e(s.japanese)}<br><i>{e(s.translation)}</i>" for s in sentences)


async def add_examples(word: str, reading: str, meaning: str, sentences: list[Sentence], deck: str) -> dict:
    """Append example sentences to the user's card(s) whose Front is `word` (any deck),
    skipping sentences already on the card. With no such card, create one in `deck`."""
    async with anki_toolset() as anki:
        found = await anki.direct_call_tool("findNotes", {"query": f'"front:{word}"'})
        note_ids = found.get("noteIds", [])

        if not note_ids:
            await anki.direct_call_tool("createDeck", {"deckName": deck})
            back = f"<b>{html.escape(reading)}</b><br>{html.escape(meaning)}<br><br>" + sentences_html(sentences)
            result = await anki.direct_call_tool(
                "addNote",
                {
                    "deckName": deck,
                    "modelName": NOTE_TYPE,
                    "fields": {"Front": html.escape(word), "Back": back},
                    "tags": ["jplearn", "vocab"],
                },
            )
            return {"action": "created new card", "deck": deck, "sentences_added": len(sentences), "anki": result}

        info = await anki.direct_call_tool("notesInfo", {"notes": note_ids})
        # notesInfo has no deck, so find each note's deck by searching deck by deck
        decks = (await anki.direct_call_tool("listDecks", {}))["decks"]
        deck_of = {}
        for d in decks:
            hits = await anki.direct_call_tool("findNotes", {"query": f'"front:{word}" "deck:{d["name"]}" -"deck:{d["name"]}::*"'})
            deck_of |= {note_id: d["name"] for note_id in hits.get("noteIds", [])}
        updated = []
        for note in info["notes"]:
            fields = note["fields"]
            if "Back" not in fields:
                updated.append({"note_id": note["noteId"], "skipped": f"note type {note['modelName']} has no Back field"})
                continue
            back = fields["Back"]["value"]
            new = [s for s in sentences if s.japanese not in back and html.escape(s.japanese) not in back]
            if new:
                await anki.direct_call_tool(
                    "updateNoteFields",
                    {"note": {"id": note["noteId"], "fields": {"Back": back + "<br><br>" + sentences_html(new)}}},
                )
            updated.append(
                {
                    "note_id": note["noteId"],
                    "deck": deck_of.get(note["noteId"], "unknown"),
                    "sentences_added": len(new),
                    "already_on_card": len(sentences) - len(new),
                }
            )
        return {"action": "updated existing card(s)", "notes": updated}


async def add_cards(deck: str, cards: list[Card]) -> dict:
    """Add cards to Anki via the MCP server. Anki skips duplicates of the Front field."""
    async with anki_toolset() as anki:
        await anki.direct_call_tool("createDeck", {"deckName": deck})
        return await anki.direct_call_tool(
            "addNotes",
            {
                "deckName": deck,
                "modelName": NOTE_TYPE,
                "tags": ["jplearn"],
                "notes": [{"fields": card_fields(c), "tags": [c.kind]} for c in cards],
            },
        )
