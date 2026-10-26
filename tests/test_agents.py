"""Agent wiring with a scripted model: routing, user context, approvals and Anki writes."""

import re

import pytest
from pydantic_ai import DeferredToolRequests
from pydantic_ai.models.test import TestModel

from jplearn import user_context
from jplearn.agents import flashcards
from jplearn.agents import orchestrator as orchestrator_module
from jplearn.agents.explainer import explainer
from jplearn.agents.flashcards import Card, Sentence, add_cards, add_examples, card_fields
from jplearn.agents.orchestrator import describe_approval, orchestrator, tools_used
from jplearn.user_context import ContextItem
from tests.scripted import answer, call, output, scripted, tool_returns

pytestmark = pytest.mark.anyio

CARD = {
    "kind": "vocab",
    "front": "食べる",
    "reading": "たべる",
    "meaning": "to eat",
    "example": "ご飯を食べる。",
    "example_translation": "I eat rice.",
}

# --- routing ---


async def test_orchestrator_delegates_to_explainer_with_users_context():
    user_context.upsert(ContextItem(name="Languages", text="I speak Mandarin", applies_to="explainer"))
    seen = {}

    def explainer_step(messages, info):
        seen["prompt"] = messages[0].parts[-1].content
        seen["instructions"] = info.instructions
        explanation = {"topic": "は vs が", "core_idea": "topic vs subject", "analogies": [], "related": [], "examples": []}
        return output(explanation)(messages, info)

    orchestrator_model = scripted(
        call("explain_concept", {"topic": "は vs が", "request": "I mix them up"}),
        answer(["Explain は vs が"], "は marks the topic."),
    )
    with orchestrator.override(model=orchestrator_model), explainer.override(model=scripted(explainer_step)):
        result = await orchestrator.run("What's the difference between は and が?")

    assert result.output.reply == "は marks the topic."
    assert tools_used(result.all_messages()) == ["explain_concept"]
    assert seen["prompt"] == "Topic: は vs が\nThe user asked: I mix them up"
    assert "I speak Mandarin" in seen["instructions"]


async def test_specialist_output_reaches_orchestrator():
    """TestModel fills the Explainer's tools and output with generated values; the
    orchestrator must receive that Explanation as the tool result."""
    orchestrator_model = scripted(call("explain_concept", {"topic": "に"}), answer([], "ok"))
    with orchestrator.override(model=orchestrator_model), explainer.override(model=TestModel()):
        result = await orchestrator.run("explain に")
    (returned,) = tool_returns(result.all_messages())
    assert returned.tool_name == "explain_concept" and returned.content.topic


# --- approvals ---


@pytest.fixture
def anki_writes(monkeypatch):
    """Replace the real Anki write with a recorder."""
    calls = []

    async def fake_add_cards(deck, cards):
        calls.append((deck, cards))
        return {"added": len(cards)}

    monkeypatch.setattr(orchestrator_module, "add_cards", fake_add_cards)
    return calls


async def _pending_add(model) -> DeferredToolRequests:
    with orchestrator.override(model=model):
        result = await orchestrator.run("Add 食べる to my Test deck")
    assert isinstance(result.output, DeferredToolRequests)
    return result


async def test_anki_write_waits_for_approval(anki_writes):
    result = await _pending_add(scripted(call("add_flashcards", {"deck": "Test", "cards": [CARD]})))
    (pending,) = result.output.approvals
    assert pending.tool_name == "add_flashcards"
    assert anki_writes == []
    summary = describe_approval(pending)
    assert "**1 cards**" in summary and "**Test**" in summary and "| vocab | 食べる | たべる |" in summary


async def test_approved_write_runs(anki_writes):
    model = scripted(call("add_flashcards", {"deck": "Test", "cards": [CARD]}), answer([], "Added 1 card."))
    result = await _pending_add(model)
    with orchestrator.override(model=model):
        final = await orchestrator.run(
            message_history=result.all_messages(), deferred_tool_results=result.output.build_results(approve_all=True)
        )
    assert final.output.reply == "Added 1 card."
    assert anki_writes == [("Test", [Card(**CARD)])]


async def test_rejected_write_never_runs(anki_writes):
    model = scripted(call("add_flashcards", {"deck": "Test", "cards": [CARD]}), answer([], "OK, not added."))
    result = await _pending_add(model)
    (pending,) = result.output.approvals
    with orchestrator.override(model=model):
        final = await orchestrator.run(
            message_history=result.all_messages(),
            deferred_tool_results=result.output.build_results(approvals={pending.tool_call_id: False}),
        )
    assert anki_writes == []
    assert "denied" in str(tool_returns(final.all_messages())[-1].content).lower()


# --- Anki write helpers ---


class FakeAnki:
    """Just enough of the Anki MCP server for flashcards.py: notes keyed by id."""

    def __init__(self, notes: dict[int, dict] | None = None):
        self.notes = notes or {}
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def direct_call_tool(self, name: str, args: dict):
        self.calls.append((name, args))
        if name == "findNotes":
            front = re.search(r'"front:([^"]+)"', args["query"]).group(1)
            deck = re.search(r'"deck:([^"]+)"', args["query"])
            ids = [i for i, n in self.notes.items() if n["front"] == front and (not deck or n["deck"] == deck.group(1))]
            return {"noteIds": ids}
        if name == "notesInfo":
            return {"notes": [self._info(i) for i in args["notes"]]}
        if name == "listDecks":
            return {"decks": [{"name": d} for d in sorted({n["deck"] for n in self.notes.values()})]}
        if name == "updateNoteFields":
            self.notes[args["note"]["id"]]["back"] = args["note"]["fields"]["Back"]
        return {"ok": True}

    def _info(self, note_id):
        note = self.notes[note_id]
        fields = {"Front": {"value": note["front"]}}
        if "back" in note:
            fields["Back"] = {"value": note["back"]}
        return {"noteId": note_id, "modelName": note.get("model", "Basic"), "fields": fields}


@pytest.fixture
def anki(monkeypatch):
    fake = FakeAnki()
    monkeypatch.setattr(flashcards, "anki_toolset", lambda: fake)
    return fake


RING = Sentence(japanese="電話が鳴る。", translation="The phone rings.")
BELL = Sentence(japanese="ベルが鳴った。", translation="The bell rang.")


async def test_add_examples_appends_only_new_sentences(anki):
    anki.notes[1] = {"front": "鳴る", "back": "なる<br>to ring<br><br>電話が鳴る。", "deck": "Japanese"}
    result = await add_examples("鳴る", "なる", "to ring", [RING, BELL], deck="jplearn")

    assert result == {
        "action": "updated existing card(s)",
        "notes": [{"note_id": 1, "deck": "Japanese", "sentences_added": 1, "already_on_card": 1}],
    }
    assert anki.notes[1]["back"].count("電話が鳴る") == 1
    assert "ベルが鳴った。<br><i>The bell rang.</i>" in anki.notes[1]["back"]


async def test_add_examples_skips_note_types_without_back(anki):
    anki.notes[1] = {"front": "鳴る", "deck": "Japanese", "model": "Cloze"}
    result = await add_examples("鳴る", "なる", "to ring", [RING], deck="jplearn")
    assert "no Back field" in result["notes"][0]["skipped"]


async def test_add_examples_creates_card_when_missing(anki):
    result = await add_examples("鳴る", "なる", "to <ring>", [RING], deck="jplearn")
    assert result["action"] == "created new card"
    name, args = anki.calls[-1]
    assert name == "addNote" and args["deckName"] == "jplearn"
    assert "to &lt;ring&gt;" in args["fields"]["Back"]  # model text is escaped before going into Anki HTML


async def test_add_cards_creates_deck_and_tags_by_kind(monkeypatch):
    fake = FakeAnki()
    monkeypatch.setattr(flashcards, "anki_toolset", lambda: fake)
    await add_cards("Test", [Card(**CARD)])
    (create, _), (add, args) = fake.calls
    assert (create, add) == ("createDeck", "addNotes")
    assert args["deckName"] == "Test" and args["notes"][0]["tags"] == ["vocab"]


def test_card_fields_escape_html():
    fields = card_fields(Card(**{**CARD, "meaning": "<script>"}))
    assert fields["Front"] == "食べる"
    assert "&lt;script&gt;" in fields["Back"] and "<script>" not in fields["Back"]
