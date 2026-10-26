"""Quizzes: romaji input, marking, the question check, the panel, and a full quiz in the web UI."""

import pytest
from pydantic_ai import ModelRetry

from jplearn.agents.orchestrator import orchestrator
from jplearn.agents.quiz import Question, Quiz, check_quiz, grade, normalize_answer, quiz_agent
from jplearn.kana import romaji_to_hiragana
from jplearn.quiz_view import FINISHED, QuizSession, active_quiz, answer, next_question, render, results_markdown
from jplearn.web import OUT_SIZE, advance_quiz, check_answer, finish_quiz, respond, sync_quiz
from tests.scripted import call, output, scripted, stream_call, stream_output, streamed

CHOICE = {
    "kind": "choice",
    "prompt": "What does 鳴る mean?",
    "options": ["to ring", "to become", "to eat"],
    "answer": "to ring",
    "explanation": "鳴(な)る is for sounds.",
}
READING = {"kind": "reading", "prompt": "How do you read this?", "word": "勉強", "answer": "べんきょう", "explanation": "Long ょう."}
FILL_IN = {"kind": "fill_in", "prompt": "私＿＿学生です。 (I am a student.)", "answer": "は", "explanation": "は marks the topic."}
QUIZ = {"title": "Basics", "questions": [CHOICE, READING]}

# --- romaji and marking ---


@pytest.mark.parametrize(
    ("romaji", "kana"),
    [
        ("benkyou", "べんきょう"),
        ("konnichiwa", "こんにちわ"),
        ("kitte", "きって"),
        ("onna", "おんな"),
        ("kin'en", "きんえん"),
        ("shinbun", "しんぶん"),
        ("chotto", "ちょっと"),
        ("jisho", "じしょ"),
    ],
)
def test_romaji_to_hiragana(romaji, kana):
    assert romaji_to_hiragana(romaji) == kana


@pytest.mark.parametrize("response", ["べんきょう", "ベンキョウ", "benkyou", " Benkyou ", "べんきょう。", "ｂｅｎｋｙｏｕ"])
def test_typed_answers_accept_kana_romaji_and_spacing(response):
    assert grade(Question(**READING), response)


@pytest.mark.parametrize("response", ["べんきょ", "", "  "])
def test_wrong_or_empty_typed_answers_fail(response):
    assert not grade(Question(**READING), response)


def test_particles_accept_how_they_sound_in_romaji():
    question = Question(**FILL_IN)
    assert grade(question, "は") and grade(question, "wa") and grade(question, "ha")
    assert not grade(question, "ga")


def test_choices_must_match_exactly():
    question = Question(**CHOICE)
    assert grade(question, "to ring") and not grade(question, "to become")


def test_also_accept():
    question = Question(**{**FILL_IN, "prompt": "雨＿＿降る。", "answer": "が", "also_accept": ["は"]})
    assert grade(question, "が") and grade(question, "は")


@pytest.mark.parametrize("response", ["みています", "見ています", "mite imasu", "miteimasu"])
def test_conjugated_answers_accept_kanji_kana_and_romaji(response):
    question = Question(kind="fill_in", prompt="テレビを＿＿。", answer="みています", explanation="")
    assert grade(question, response)


def test_normalize_answer():
    assert normalize_answer("  タベル。 ") == "たべる"


# --- question check ---


def test_valid_quiz_passes():
    quiz = Quiz(title="Mix", questions=[Question(**CHOICE), Question(**READING), Question(**FILL_IN)])
    assert check_quiz(quiz) is quiz


@pytest.mark.parametrize(
    ("question", "problem"),
    [
        ({**CHOICE, "answer": "to sound"}, "must be one of its options"),
        ({**CHOICE, "options": ["to ring", "to ring"]}, "duplicate options"),
        ({**READING, "answer": "べんきょ"}, "reading of 勉強 is べんきょう"),
        ({**READING, "prompt": "Read 勉強 (べんきょう)"}, "gives away the reading"),
        ({**READING, "word": None}, "needs `word`"),
        ({**FILL_IN, "prompt": "私は学生です。"}, "needs ＿＿"),
    ],
)
def test_bad_questions_are_sent_back(question, problem):
    with pytest.raises(ModelRetry, match=problem):
        check_quiz(Quiz(title="Bad", questions=[Question(**question)]))


@pytest.mark.anyio
async def test_quiz_maker_fixes_a_rejected_quiz():
    bad = {"title": "Basics", "questions": [{**READING, "answer": "べんきょ"}]}
    with quiz_agent.override(model=scripted(output(bad), output(QUIZ))):
        result = await quiz_agent.run("quiz me")
    assert result.output.questions[1].answer == "べんきょう"


# --- the panel ---


def _session():
    return QuizSession(id="call-1", quiz=Quiz(**QUIZ))


def _panel(values):
    return dict(zip(["panel", "progress", "question", "choices", "typed", "feedback", "check", "next"], values))


def test_choice_question_shows_options_and_is_marked_on_click():
    panel = _panel(render(_session()))
    assert panel["panel"].visible and panel["choices"].visible and not panel["typed"].visible
    assert not panel["check"].visible  # clicking an option marks it
    assert "Question 1 of 2 · 0 correct" in panel["progress"]


def test_answered_question_shows_feedback_and_next():
    panel = _panel(render(answer(_session(), "to become")))
    assert panel["feedback"].startswith("❌ **Not quite.** The answer is **to ring**")
    assert "<ruby>鳴" in panel["feedback"]  # furigana in the explanation
    assert panel["next"].visible and panel["next"].value == "Next question →"
    assert panel["choices"].interactive is False
    assert "step wrong" in panel["progress"]


def test_typed_question_and_last_question_label():
    session = answer(next_question(answer(_session(), "to ring")), "benkyou")
    panel = _panel(render(session))
    assert panel["typed"].visible and not panel["choices"].visible
    assert panel["feedback"].startswith("✅ **Correct!**")
    assert panel["next"].value == "See results"
    assert "2 correct" in panel["progress"]


def test_results_list_every_question():
    session = answer(_session(), "to become")
    markdown = results_markdown(session)
    assert "Basics · 0/2" in markdown
    assert "❌ What does 鳴る mean?: you said to become, answer **to ring**" in markdown
    assert "⏭ 勉強 (not answered)" in markdown


# --- a whole quiz in the web UI ---


def _state():
    return [], [], None, {}, []


@pytest.mark.anyio
async def test_full_quiz_flow_in_the_web_ui():
    feedback_prompts = []

    async def feedback(messages, info):
        feedback_prompts.append(messages[-1].parts[-1].content)
        async for chunk in stream_output('{"plan": [], "reply": "Great job!"}')(messages, info):
            yield chunk

    orchestrator_model = streamed(
        stream_call("start_quiz", {"request": "basics"}),
        stream_output('{"plan": ["Make a quiz"], "reply": "Your quiz is ready below."}'),
        feedback,
    )
    with orchestrator.override(model=orchestrator_model), quiz_agent.override(model=scripted(output(QUIZ))):
        # 1. Ask for a quiz: the panel opens on question 1
        async for update in respond("quiz me", *_state(), False):
            box, chat, history, pending, status, log, *_ = update
        session, *values = sync_quiz(history, None)
        assert session.quiz.title == "Basics" and _panel(values)["panel"].visible
        assert "べんきょう" not in str(chat)  # answers never appear in the chat

        # 2. Answer both questions (the second in romaji)
        session, *_ = check_answer(session, "to ring", "")
        (update,) = [u async for u in advance_quiz(session, chat, history, pending, status, log, False)]
        session = update[OUT_SIZE]  # values are [*out, quiz_state, *quiz_ui]
        assert session.index == 1
        session, *values = check_answer(session, None, "benkyou")
        assert _panel(values)["feedback"].startswith("✅")

        # 3. See results: the panel closes and the tutor gives feedback
        async for update in advance_quiz(session, chat, history, pending, status, log, False):
            pass
        _box, chat, history = update[:3]
        quiz_state, panel = update[OUT_SIZE], update[OUT_SIZE + 1]

    assert quiz_state is None and not panel.visible
    results = [m for m in chat if m["role"] == "user"][-1]
    assert results["content"].startswith("**📝 Quiz finished: Basics · 2/2**")
    assert chat[-1]["content"] == "Great job!"
    assert feedback_prompts[0].startswith(FINISHED.format(session.id))
    assert active_quiz(history) is None  # finished quizzes don't reopen
    assert sync_quiz(history, None)[0] is None


@pytest.mark.anyio
async def test_unfinished_quiz_reopens_with_the_chat():
    model = scripted(call("start_quiz", {"request": "basics"}), output({"plan": [], "reply": "Ready."}))
    with orchestrator.override(model=model), quiz_agent.override(model=scripted(output(QUIZ))):
        result = await orchestrator.run("quiz me")
    assert active_quiz(result.all_messages()).quiz.title == "Basics"


@pytest.mark.anyio
async def test_ending_a_quiz_rejects_a_waiting_approval():
    card = {"kind": "vocab", "front": "鳴る", "reading": "なる", "meaning": "to ring", "example": "鳴る。", "example_translation": "Rings."}
    model = streamed(
        stream_call("add_flashcards", {"deck": "Test", "cards": [card]}),
        stream_output('{"plan": [], "reply": "OK."}'),
    )
    with orchestrator.override(model=model):
        async for update in respond("add a card", *_state(), False):
            box, chat, history, pending, status, log, *_ = update
        assert pending is not None
        async for update in finish_quiz(answer(_session(), "to ring"), chat, history, pending, status, log, False):
            _box, chat, history, pending, *_ = update
    assert pending is None and chat[-1]["content"] == "OK."
