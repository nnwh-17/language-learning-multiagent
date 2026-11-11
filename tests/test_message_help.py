"""The Translate and Words buttons on chat messages, and the side panel they open."""

import json

import gradio as gr
import pytest

from jplearn import message_help_view as view
from jplearn.agents.message_help import message_translator, word_helper
from tests.scripted import output, scripted

MESSAGE = "Try this one:\n\n猫が魚を食べた。\n\n*The cat ate the fish.*"
TRANSLATION = {"lines": [{"japanese": "猫が魚を食べた。", "english": "The cat ate the fish."}]}
NOTES = {
    "notes": [
        {
            "word": "食べた",
            "reading": "たべた",
            "meaning": "ate",
            "here": "Past form of 食べる (to eat).",
            "example": "パンを食べた。",
            "example_english": "I ate bread.",
        }
    ]
}


def payload(mode: str, text: str = MESSAGE, selection: str = "") -> str:
    return json.dumps({"mode": mode, "text": text, "selection": selection, "nonce": 1})


def recording(value: dict, seen: list[str]):
    def step(messages, info):
        seen.append(messages[0].parts[-1].content)
        return output(value)(messages, info)

    return scripted(step)


def test_a_bad_payload_is_ignored():
    assert view.parse_request("not json") == view.Request()


def test_opening_a_new_message_resets_the_panel():
    message, preview, translation, words, notes, sidebar, tabs, menu = view.open_panel(
        payload("words", selection="食べた"), current="an older message"
    )
    assert message == MESSAGE and preview.startswith("> Try this one: 猫が魚を食べた。")
    assert translation == view.TRANSLATE_HINT and words == "食べた" and notes == ""
    assert sidebar.open is True and menu.open is False and tabs.selected == view.TAB_ID


def test_reopening_the_same_message_keeps_its_results():
    _, _, translation, words, notes, *_ = view.open_panel(payload("translate"), current=MESSAGE)
    skipped = type(gr.skip())
    assert all(isinstance(value, skipped) for value in (translation, words, notes))
    # ...and the Translate button doesn't translate it again
    assert not view.after_open(payload("translate"), "**猫が魚を食べた。**  \nThe cat ate the fish.")
    assert view.after_open(payload("translate"), view.TRANSLATE_HINT)
    assert not view.after_open(payload("words"), view.TRANSLATE_HINT)


@pytest.mark.anyio
async def test_translating_a_message():
    seen = []
    with message_translator.override(model=recording(TRANSLATION, seen)):
        updates = [u async for u in view.translate(MESSAGE)]
    assert updates[0] == view.TRANSLATING
    assert updates[-1] == "**猫が魚を食べた。**  \nThe cat ate the fish."
    assert "猫が魚を食べた。" in seen[0]


@pytest.mark.anyio
async def test_a_message_without_japanese_needs_no_model():
    updates = [u async for u in view.translate("You're welcome!")]
    assert updates == ["_This message has no Japanese to translate._"]


@pytest.mark.anyio
async def test_explaining_pasted_words_is_grounded_in_the_dictionary():
    seen = []
    with word_helper.override(model=recording(NOTES, seen)):
        updates = [u async for u in view.explain_words(MESSAGE, "食べた")]
    assert "- 食べ → 食べる (たべる) [vocab]: to eat" in updates[0]  # shown while waiting
    assert "Words the learner wants explained: 食べた" in seen[0]
    assert "- 食べ → 食べる (たべる) [vocab]: to eat" in seen[0]
    assert updates[-1].startswith("#### 食べた (たべた)\n**ate**. Past form of 食べる (to eat).")


@pytest.mark.anyio
async def test_the_dictionary_still_shows_if_the_model_fails():
    def fail(messages, info):
        raise RuntimeError("model down")

    with word_helper.override(model=scripted(fail)):
        updates = [u async for u in view.explain_words(MESSAGE, "食べた")]
    assert updates[-1].startswith("⚠️") and "食べる (たべる) [vocab]: to eat" in updates[-1]


@pytest.mark.anyio
async def test_explaining_needs_words():
    assert [u async for u in view.explain_words(MESSAGE, "  ")] == ["Paste a word or phrase from the message first."]
