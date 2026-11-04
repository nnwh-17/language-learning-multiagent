"""The Read & translate tab: highlighting, breakdowns without a model, checking a translation,
and the quiz and cards made from the highlights."""

from types import SimpleNamespace

import pytest

from jplearn import quiz_view, reader_view
from jplearn.agents.flashcards import Card, card_fields
from jplearn.agents.quiz import check_quiz, grade
from jplearn.agents.translation import translation_checker
from jplearn.config import DEFAULT_DECK
from jplearn.reader_view import (
    START_SIZE,
    Reading,
    add_highlight,
    breakdown_markdown,
    check_translation,
    draft_cards,
    end_quiz,
    make_quiz,
    on_select,
    remove_highlight,
    render_text,
    start_quiz,
    start_reading,
    study_items,
)
from tests.scripted import output, scripted

# Offsets: 猫0 が1 魚2 を3 食べ4-6 て6 しまっ7-10 た10 。11 | 毎日12-14 勉強14-16 し16 て17 いる18-20 。20
TEXT = "猫が魚を食べてしまった。毎日勉強している。"
REVIEW = {
    "verdict": "mostly right",
    "summary": "Good effort!",
    "reference": "The cat went and ate the fish. I study every day.",
    "got_right": ["studying every day"],
    "mistakes": [
        {
            "japanese": "食べてしまった",
            "you_wrote": "tried to eat",
            "problem": "〜てしまう means it happened (regrettably), not 'try'.",
            "better": "went and ate",
            "kind": "grammar",
        }
    ],
}


def _event(**data):
    """Stands in for the gr.EventData the pane's script sends."""
    return SimpleNamespace(**data)


# --- highlighting ---


def test_selections_snap_to_whole_tokens():
    reading = add_highlight(Reading(text=TEXT), 5, 8)  # べてし
    assert [(h.start, h.end) for h in reading.highlights] == [(4, 10)]  # 食べてしまっ


def test_overlapping_highlights_merge_and_punctuation_alone_is_ignored():
    reading = add_highlight(add_highlight(Reading(text=TEXT), 0, 1), 2, 3)
    assert [(h.start, h.end) for h in reading.highlights] == [(0, 1), (2, 3)]  # neighbours stay apart
    reading = add_highlight(reading, 0, 3)
    assert [(h.start, h.end) for h in reading.highlights] == [(0, 3)]
    assert add_highlight(reading, 11, 12).highlights == reading.highlights  # just 。


def test_clicking_a_highlight_removes_it():
    reading = add_highlight(add_highlight(Reading(text=TEXT), 0, 1), 14, 16)
    assert [(h.start, h.end) for h in remove_highlight(reading, 15).highlights] == [(0, 1)]


def test_select_events_from_the_pane():
    reading, pane, breakdown = on_select(Reading(text=TEXT), _event(action="add", start=14, end=16))
    assert '<span data-s="14" class="hl you" title="べんきょう">勉強</span>' in pane
    assert "**勉強**（べんきょう） study" in breakdown
    reading, pane, breakdown = on_select(reading, _event(action="remove", start=14, end=14))
    assert not reading.highlights and "hl" not in pane and "Nothing highlighted" in breakdown


def test_render_keeps_every_character_with_its_offset():
    html = render_text(Reading(text="猫<b>\n猫"))
    assert '<span data-s="1">&lt;</span>' in html and '<span data-s="3">&gt;\n</span>' in html
    assert '<span data-s="5" title="ねこ">猫</span>' in html
    assert "data-len='6'" in html


# --- breakdown without a model ---


def test_breakdown_explains_words_and_te_patterns():
    reading = add_highlight(Reading(text=TEXT), 4, 11)  # 食べてしまった
    items = study_items(reading)
    assert [(i.kind, i.key) for i in items] == [("vocab", "食べる"), ("grammar", "〜てしまう"), ("grammar", "た")]
    assert items[0].meaning == "to eat" and items[0].note.startswith("食べ, continuative")
    assert items[1].surface == "てしまっ" and "regret" in items[1].meaning
    assert "past tense" in items[2].meaning
    markdown = breakdown_markdown(reading)
    assert markdown.startswith("**食べてしまった**") and "**〜てしまう** _grammar_" in markdown


def test_particles_get_grammar_notes_not_dictionary_entries():
    (item,) = study_items(add_highlight(Reading(text=TEXT), 1, 2))
    assert (item.key, item.particle) == ("が", True) and "subject marker" in item.meaning


def test_repeated_items_are_listed_once():
    reading = add_highlight(add_highlight(Reading(text="食べた。食べた。"), 0, 2), 4, 6)
    assert len(study_items(reading)) == 1
    assert "- 食べる: _see above_" in breakdown_markdown(reading)


# --- the tab ---


def test_start_reading_shows_the_text_and_rejects_bad_input():
    values = start_reading(f"  {TEXT}  ")
    assert len(values) == START_SIZE
    reading, status, workspace, pane = values[:4]
    assert reading.text == TEXT and status == "" and workspace.visible and "data-s" in pane
    assert start_reading("hello")[1] == "Paste some Japanese text first."
    assert "paste up to" in start_reading("猫" * (reader_view.MAX_CHARS + 1))[1]


@pytest.mark.anyio
async def test_checking_a_translation_highlights_the_mistakes():
    reading = add_highlight(Reading(text=TEXT), 14, 16)  # 勉強
    seen = []

    def review(messages, info):
        seen.append(messages[0].parts[-1].content)
        return output(REVIEW)(messages, info)

    with translation_checker.override(model=scripted(review)):
        updates = [u async for u in check_translation(reading, "The cat tried to eat the fish. I study daily.")]
    reading, feedback, pane, breakdown = updates[-1]
    prompt = seen[0]
    assert "Highlighted by the learner as unknown: 勉強" in prompt
    assert "- 食べ → 食べる (たべる) [vocab]: to eat" in prompt  # grounded in the tokenizer + JMdict
    assert "**Mostly right.**" in feedback and "you wrote “tried to eat”" in feedback
    assert [(h.start, h.end, h.source) for h in reading.highlights] == [(4, 11, "mistake"), (14, 16, "you")]
    assert "class=\"hl mistake\"" in pane and "_from your translation_" in breakdown


@pytest.mark.anyio
async def test_check_needs_a_translation():
    updates = [u async for u in check_translation(Reading(text=TEXT), "  ")]
    assert updates[-1][1].startswith("Write your translation first")


# --- quiz and cards, without a model ---


def test_quiz_from_highlights_passes_the_quiz_check():
    reading = add_highlight(add_highlight(Reading(text=TEXT), 1, 2), 4, 11)  # が, 食べてしまった
    quiz = make_quiz(reading)
    assert check_quiz(quiz) is quiz  # options contain the answer, readings match the tokenizer
    kinds = [(q.kind, q.answer) for q in quiz.questions]
    assert ("fill_in", "が") in kinds and ("reading", "たべる") in kinds
    fill_in = next(q for q in quiz.questions if q.kind == "fill_in")
    assert fill_in.prompt.startswith("猫＿＿魚を食べてしまった。") and grade(fill_in, "ga")
    pattern = next(q for q in quiz.questions if "〜てしまう" in q.prompt)
    assert pattern.kind == "choice" and len(pattern.options) == 4 and "regret" in pattern.answer


def test_no_quiz_without_highlights():
    assert make_quiz(Reading(text=TEXT)) is None
    assert start_quiz(Reading(text=TEXT))[0] == "Highlight something in the text first."


def test_quiz_in_the_tab_shows_results_at_the_end():
    status, session, panel, *_ = start_quiz(add_highlight(Reading(text=TEXT), 14, 16))
    assert status == "" and panel.visible
    question = session.question
    session, *_ = quiz_view.check_answer(session, question.answer, question.answer)
    state, panel, *rest = end_quiz(session)
    assert state is None and not panel.visible and rest[-1].startswith("**📝 Quiz finished: Your highlights · 1/")


def test_cards_use_the_items_sentence():
    reading = add_highlight(Reading(text=TEXT), 4, 11)
    cards = draft_cards(reading)
    assert [c.front for c in cards] == ["食べる", "〜てしまう", "た"]
    assert cards[0].reading == "たべる" and cards[0].example == "猫が魚を食べてしまった。"
    assert cards[0].example_translation == ""  # the translation is of the whole two-sentence text


def test_one_sentence_cards_get_the_reviewed_translation():
    reading = add_highlight(Reading(text="勉強した。", review=REVIEW), 0, 2)
    (card,) = draft_cards(reading)
    assert card.example == "勉強した。" and card.example_translation == REVIEW["reference"]


@pytest.mark.anyio
async def test_add_to_anki_adds_exactly_the_previewed_cards(monkeypatch):
    added = []

    async def fake_add_cards(deck, cards):
        added.append((deck, cards))
        return {"ok": True}

    monkeypatch.setattr(reader_view, "add_cards", fake_add_cards)
    cards = draft_cards(add_highlight(Reading(text=TEXT), 14, 16))
    updates = [u async for u in reader_view.add_to_anki(cards, " ")]
    assert added == [(DEFAULT_DECK, cards)] and updates[-1].startswith("✅ Sent 1 card to")


def test_card_without_an_example():
    card = Card(kind="grammar", front="〜てしまう", reading="", meaning="regret", example="", example_translation="")
    assert card_fields(card)["Back"] == "regret"
