"""The web UI's turn handling: streaming, the locked composer, approvals and errors."""

import anyio
import pytest
from pydantic_ai import PartDeltaEvent, PartStartEvent
from pydantic_ai.messages import TextPart, TextPartDelta, ToolCallPart, ToolCallPartDelta
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from jplearn.agents import orchestrator as orchestrator_module
from jplearn.agents.orchestrator import orchestrator, stream_reply
from jplearn.web import progress_message, respond, steps_message, with_furigana
from tests.scripted import stream_call, stream_output, streamed, tool_returns

CARD = {
    "kind": "vocab",
    "front": "食べる",
    "reading": "たべる",
    "meaning": "to eat",
    "example": "ご飯を食べる。",
    "example_translation": "I eat rice.",
}

# --- formatting helpers ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("食(た)べる", "<ruby>食<rp>(</rp><rt>た</rt><rp>)</rp></ruby>べる"),
        ("日本語（にほんご）", "<ruby>日本語<rp>(</rp><rt>にほんご</rt><rp>)</rp></ruby>"),
        ("鳴りました (polite past)", "鳴りました (polite past)"),  # English in brackets is left alone
        ("ベル(べる)", "ベル(べる)"),  # only kanji get readings
    ],
)
def test_with_furigana(text, expected):
    assert with_furigana(text) == expected


def test_steps_message_names_specialists_once_in_order():
    message = steps_message(["Look it up"], ["analyze_japanese", "lookup_word", "analyze_japanese"], 2.04)
    assert message["content"] == "1. Look it up\n\n**Used:** Analyzer → JMdict"
    assert message["metadata"] == {"title": "How I answered", "status": "done", "duration": 2.0}


def test_steps_message_is_skipped_for_small_talk():
    assert steps_message([], [], 1.0) is None


def test_progress_message_names_running_specialists():
    assert progress_message({"orchestrator": "running"})["metadata"]["title"] == "Thinking..."
    status = {"orchestrator": "running", "explainer": "running", "jmdict": "done"}
    assert progress_message(status)["metadata"]["title"] == "Working: Explainer"


# --- stream_reply ---


async def _replies(events) -> list[str]:
    seen = []

    async def gen():
        for event in events:
            yield event

    await stream_reply(seen.append)(None, gen())
    return seen


@pytest.mark.anyio
async def test_stream_reply_reads_output_tool_arguments():  # LiteLLM path
    events = [
        PartStartEvent(index=0, part=ToolCallPart(tool_name="final_result", args='{"plan": [], "reply": "Hi')),
        PartDeltaEvent(index=0, delta=ToolCallPartDelta(args_delta=' there"}')),
    ]
    assert await _replies(events) == ["Hi", "Hi there"]


@pytest.mark.anyio
async def test_stream_reply_reads_native_json_text_and_ignores_remarks():  # Claude API path
    events = [
        PartStartEvent(index=0, part=TextPart(content="Let me check.")),
        PartStartEvent(index=1, part=TextPart(content='{"plan": ["x"], "re')),
        PartDeltaEvent(index=1, delta=TextPartDelta(content_delta='ply": "鳴る means')),
        PartDeltaEvent(index=1, delta=TextPartDelta(content_delta=' to ring"}')),
    ]
    assert await _replies(events) == ["鳴る means", "鳴る means to ring"]


@pytest.mark.anyio
async def test_stream_reply_ignores_other_tool_calls():
    events = [PartStartEvent(index=0, part=ToolCallPart(tool_name="lookup_word", args='{"reply": "no"}'))]
    assert await _replies(events) == []


# --- a whole turn through respond() ---


def _state():
    """Fresh (chat, history, pending, status, log) for one browser tab."""
    return [], [], None, {}, []


def _unpack(update):
    box, chat, history, pending, status, log, _arch, _log_html, approve_btn, _reject_btn = update
    return box, chat, history, pending, approve_btn


@pytest.mark.anyio
async def test_reply_streams_in_while_composer_is_locked():
    gate = anyio.Event()

    async def answer(messages, info):
        name = info.output_tools[0].name
        yield {0: DeltaToolCall(name=name, json_args='{"plan": ["Greet"], "reply": "Hel')}
        await gate.wait()  # hold the rest until the test has seen the partial reply
        yield {0: DeltaToolCall(json_args='lo 食(た)べる"}')}

    partials = []
    with anyio.fail_after(10), orchestrator.override(model=streamed(answer)):
        async for update in respond("hi", *_state(), False):
            box, chat, *_ = _unpack(update)
            if box.interactive is False and chat[-1]["content"] == "Hel":
                partials.append(chat[-1]["content"])
                gate.set()

    assert partials == ["Hel"]
    assert box.interactive is True  # unlocked when the turn ends
    user, steps, reply = chat
    assert user == {"role": "user", "content": "hi"}
    assert steps["metadata"]["title"] == "How I answered"
    assert reply["content"] == "Hello <ruby>食<rp>(</rp><rt>た</rt><rp>)</rp></ruby>べる"


@pytest.mark.anyio
async def test_replying_instead_of_approving_rejects_with_reason(monkeypatch):
    async def fail_if_called(deck, cards):
        raise AssertionError("must not write to Anki")

    monkeypatch.setattr(orchestrator_module, "add_cards", fail_if_called)
    seen = []

    async def final(messages, info):
        seen.extend(tool_returns(messages))
        async for chunk in stream_output('{"plan": [], "reply": "Which deck?"}')(messages, info):
            yield chunk

    model = streamed(stream_call("add_flashcards", {"deck": "Test", "cards": [CARD]}), final)
    chat, history, pending, status, log = _state()
    with orchestrator.override(model=model):
        async for update in respond("make a card for 食べる", chat, history, pending, status, log, False):
            box, chat, history, pending, approve_btn = _unpack(update)
        assert pending is not None and approve_btn.visible
        assert box.placeholder.startswith("Approve or reject")

        async for update in respond("use the Travel deck", chat, history, pending, {}, log, False):
            box, chat, history, pending, approve_btn = _unpack(update)

    assert pending is None and not approve_btn.visible
    assert "User replied instead: use the Travel deck" in str(seen[-1].content)
    assert chat[-1]["content"] == "Which deck?"


@pytest.mark.anyio
async def test_errors_are_shown_politely_and_unlock_the_composer():
    async def broken(messages, info):
        raise RuntimeError("proxy down")
        yield  # makes this an async generator

    with orchestrator.override(model=FunctionModel(stream_function=broken)):
        async for update in respond("hi", *_state(), False):
            box, chat, *_ = _unpack(update)

    assert box.interactive is True
    apology, details = chat[-2:]
    assert apology["content"].startswith("⚠️ Sorry")
    assert details["metadata"]["title"] == "Error details" and "proxy down" in details["content"]


@pytest.mark.anyio
async def test_empty_message_does_nothing():
    async for update in respond("   ", *_state(), False):
        box, chat, *_ = _unpack(update)
    assert chat == [] and box.interactive is True
