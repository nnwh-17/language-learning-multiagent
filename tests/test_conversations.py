"""Saved chats: storage, resuming a conversation, and the web sidebar handlers."""

import time

import pytest
from pydantic_ai import DeferredToolRequests

from jplearn import conversations
from jplearn.agents import orchestrator as orchestrator_module
from jplearn.agents.orchestrator import orchestrator
from jplearn.web import delete_chat, open_chat, reopen_latest_chat, save_chat
from tests.scripted import answer, call, scripted

CARD = {
    "kind": "vocab",
    "front": "食べる",
    "reading": "たべる",
    "meaning": "to eat",
    "example": "ご飯を食べる。",
    "example_translation": "I eat rice.",
}


def _gradio(role: str, text: str) -> dict:
    """A message in the form Gradio passes back to handlers."""
    return {"role": role, "metadata": None, "content": [{"text": text, "type": "text"}], "options": None}


async def _conversation(*steps, prompt="hi"):
    with orchestrator.override(model=scripted(*steps)):
        return await orchestrator.run(prompt)


# --- storage ---


@pytest.mark.anyio
async def test_save_and_load_round_trip():
    result = await _conversation(answer([], "こんにちは"))
    messages = [_gradio("user", "hi"), _gradio("assistant", "こんにちは")]
    chat_id = conversations.save(None, messages, result.all_messages())

    saved = conversations.load(chat_id)
    assert saved.messages == messages
    assert saved.history == result.all_messages()
    assert saved.title == "hi" and saved.pending == []


@pytest.mark.anyio
async def test_resumed_history_reaches_the_model():
    first = await _conversation(answer([], "Nice to meet you, Sam."), prompt="My name is Sam")
    chat_id = conversations.save(None, [_gradio("user", "My name is Sam")], first.all_messages())
    seen = []

    def remember(messages, info):
        seen.extend(messages)
        return answer([], "Sam")(messages, info)

    with orchestrator.override(model=scripted(remember)):
        await orchestrator.run("What's my name?", message_history=conversations.load(chat_id).history)
    assert "My name is Sam" in str(seen[0])


def test_title_is_first_user_message_on_one_short_line():
    long = "Explain the difference between は and が\nwith lots of examples please, thank you"
    chat_id = conversations.save(None, [_gradio("user", long)], [])
    title = conversations.load(chat_id).title
    assert "\n" not in title and len(title) == conversations.TITLE_LENGTH and title.endswith("…")


def test_list_is_newest_first_and_skips_broken_files(chats_dir):
    old = conversations.save(None, [_gradio("user", "old")], [])
    time.sleep(0.01)
    new = conversations.save(None, [_gradio("user", "new")], [])
    (chats_dir / "broken.json").write_text("{not json", encoding="utf-8")
    assert [c.id for c in conversations.list_chats()] == [new, old]


def test_saving_again_updates_the_same_chat():
    chat_id = conversations.save(None, [_gradio("user", "a")], [])
    assert conversations.save(chat_id, [_gradio("user", "a"), _gradio("assistant", "b")], []) == chat_id
    assert len(conversations.list_chats()) == 1


def test_delete_and_missing_chats():
    chat_id = conversations.save(None, [_gradio("user", "a")], [])
    conversations.delete(chat_id)
    assert conversations.load(chat_id) is None
    conversations.delete(chat_id)  # deleting twice is fine


@pytest.mark.parametrize("bad_id", ["../secrets", "a/b", "", "x.json"])
def test_ids_cannot_escape_the_chats_folder(bad_id):
    with pytest.raises(ValueError):
        conversations.load(bad_id)


# --- a pending approval survives a restart ---


@pytest.mark.anyio
async def test_pending_approval_can_be_approved_after_reload(monkeypatch):
    written = []

    async def fake_add_cards(deck, cards):
        written.append(deck)
        return {"added": len(cards)}

    monkeypatch.setattr(orchestrator_module, "add_cards", fake_add_cards)
    model = scripted(call("add_flashcards", {"deck": "Test", "cards": [CARD]}), answer([], "Added."))
    with orchestrator.override(model=model):
        first = await orchestrator.run("card for 食べる")
        assert isinstance(first.output, DeferredToolRequests)
        chat_id = conversations.save(None, [_gradio("user", "card for 食べる")], first.all_messages(), first.output)

        saved = conversations.load(chat_id)
        pending = conversations.pending_approvals(saved)
        assert [c.tool_call_id for c in pending.approvals] == [c.tool_call_id for c in first.output.approvals]

        final = await orchestrator.run(
            message_history=saved.history, deferred_tool_results=pending.build_results(approve_all=True)
        )
    assert final.output.reply == "Added." and written == ["Test"]


# --- web sidebar handlers ---


def _shown(values):
    """Pick (chat window, pending, approve button, chat id) out of open_chat's values."""
    box, chat, history, pending, status, log, _arch, _log_html, approve_btn, _reject_btn, chat_id = values[:11]
    return chat, pending, approve_btn, chat_id


@pytest.mark.anyio
async def test_save_then_reopen_in_a_new_tab():
    result = await _conversation(answer([], "やあ"))
    messages = [_gradio("user", "hi"), _gradio("assistant", "やあ")]
    chat_id, chat_list = save_chat(None, messages, result.all_messages(), None)
    assert chat_list.value == chat_id and chat_list.choices == [("hi", chat_id)]

    chat, pending, approve_btn, reopened = _shown(reopen_latest_chat(False))
    assert (chat, pending, reopened) == (messages, None, chat_id)
    assert not approve_btn.visible


def test_empty_chat_is_not_saved():
    chat_id, _ = save_chat(None, [], [], None)
    assert chat_id is None and conversations.list_chats() == []


@pytest.mark.anyio
async def test_reopened_chat_shows_approval_buttons():
    first = await _conversation(call("add_flashcards", {"deck": "Test", "cards": [CARD]}))
    chat_id, _ = save_chat(None, [_gradio("user", "card")], first.all_messages(), first.output)
    _chat, pending, approve_btn, _ = _shown(open_chat(chat_id, False))
    assert pending is not None and approve_btn.visible


def test_delete_chat_starts_a_new_one():
    chat_id, _ = save_chat(None, [_gradio("user", "bye")], [], None)
    values = delete_chat(chat_id, False)
    chat, _pending, _btn, new_id = _shown(values)
    assert (chat, new_id) == ([], None)
    assert values[-1].choices == []  # the sidebar list is empty again
