"""The web UI's quiz panel: one question at a time, marked as soon as it's answered.

A quiz arrives as the metadata of a ``start_quiz`` tool result in the chat history, so it is
saved and reopened with the chat. The panel keeps a ``QuizSession`` (which question, what
was answered); when the learner finishes, ``results_prompt`` goes to the orchestrator for
feedback and marks the quiz finished in the history.
"""

import html

import gradio as gr
from pydantic import BaseModel
from pydantic_ai.messages import ModelMessage, ToolReturnPart, UserPromptPart

from jplearn.agents.quiz import Question, Quiz, grade
from jplearn.kana import with_furigana

FINISHED = "[quiz {} finished]"  # starts the results message; marks the quiz as done

PLACEHOLDERS = {
    "reading": "Type the reading in hiragana or romaji, then press Enter",
    "fill_in": "Type what goes in the blank (kana or romaji), then press Enter",
    "choice": "",
}


class Answer(BaseModel):
    response: str
    correct: bool


class QuizSession(BaseModel):
    id: str  # tool_call_id of the start_quiz call that made the quiz
    quiz: Quiz
    index: int = 0  # the question showing
    answers: list[Answer] = []  # one per question answered so far

    @property
    def question(self) -> Question:
        return self.quiz.questions[self.index]

    @property
    def checked(self) -> bool:
        """Whether the question showing has been answered."""
        return len(self.answers) > self.index

    @property
    def is_last(self) -> bool:
        return self.index == len(self.quiz.questions) - 1

    @property
    def score(self) -> int:
        return sum(answer.correct for answer in self.answers)


def active_quiz(history: list[ModelMessage]) -> QuizSession | None:
    """A fresh session for the latest quiz in the chat, unless it has been finished."""
    quizzes = [
        part
        for message in history
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name == "start_quiz" and part.metadata
    ]
    if not quizzes:
        return None
    latest = quizzes[-1]
    marker = FINISHED.format(latest.tool_call_id)
    finished = any(
        isinstance(part, UserPromptPart) and isinstance(part.content, str) and part.content.startswith(marker)
        for message in history
        for part in message.parts
    )
    return None if finished else QuizSession(id=latest.tool_call_id, quiz=Quiz.model_validate(latest.metadata))


def answer(session: QuizSession, response: str) -> QuizSession:
    """Record and mark the answer to the question showing."""
    correct = grade(session.question, response)
    return session.model_copy(update={"answers": [*session.answers, Answer(response=response, correct=correct)]})


def next_question(session: QuizSession) -> QuizSession:
    return session.model_copy(update={"index": session.index + 1})


# --- rendering: values for [panel, progress, question, choices, typed, feedback, check, next] ---


def render(session: QuizSession | None, notice: str = "") -> tuple:
    if session is None:
        return (
            gr.Column(visible=False), "", "",
            gr.Radio(choices=[], value=None, visible=False), gr.Textbox(value="", visible=False),
            "", gr.Button(visible=False), gr.Button(visible=False),
        )
    question, checked = session.question, session.checked
    given = session.answers[session.index] if checked else None
    choices = gr.Radio(
        choices=question.options,
        value=given.response if given else None,
        visible=question.kind == "choice",
        interactive=not checked,
    )
    typed = gr.Textbox(
        value=given.response if given else "",
        visible=question.kind != "choice",
        interactive=not checked,
        placeholder=PLACEHOLDERS[question.kind],
    )
    return (
        gr.Column(visible=True),
        _progress(session),
        _question(question),
        choices,
        typed,
        notice or _feedback(question, given),
        gr.Button(visible=not checked and question.kind != "choice"),  # choices are marked on click
        gr.Button(visible=checked, value="See results" if session.is_last else "Next question →"),
    )


def _progress(session: QuizSession) -> str:
    steps = []
    for i in range(len(session.quiz.questions)):
        if i < len(session.answers):
            steps.append("right" if session.answers[i].correct else "wrong")
        else:
            steps.append("current" if i == session.index else "")
    bar = "".join(f"<span class='step {step}'></span>" for step in steps)
    position = f"Question {session.index + 1} of {len(session.quiz.questions)} · {session.score} correct"
    return (
        f"<div class='quiz-head'><b>📝 {html.escape(session.quiz.title)}</b><span>{position}</span></div>"
        f"<div class='quiz-bar'>{bar}</div>"
    )


def _question(question: Question) -> str:
    text = question.prompt
    if question.kind == "reading" and question.word and question.word not in text:
        text += f"\n\n## {question.word}"
    return text


def _feedback(question: Question, given: Answer | None) -> str:
    if given is None:
        return ""
    explanation = with_furigana(question.explanation)
    if given.correct:
        return f"✅ **Correct!** {explanation}"
    also = f" (or {', '.join(question.also_accept)})" if question.also_accept else ""
    return f"❌ **Not quite.** The answer is **{question.answer}**{also}.\n\n{explanation}"


# --- results ---


def _short(text: str, limit: int = 70) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def results_markdown(session: QuizSession) -> str:
    """The results as the learner's chat message."""
    total = len(session.quiz.questions)
    lines = [f"**📝 Quiz finished: {session.quiz.title} · {session.score}/{total}**", ""]
    for i, question in enumerate(session.quiz.questions):
        label = _short(question.word or question.prompt)
        if i >= len(session.answers):
            lines.append(f"{i + 1}. ⏭ {label} (not answered)")
        elif session.answers[i].correct:
            lines.append(f"{i + 1}. ✅ {label}: {session.answers[i].response}")
        else:
            lines.append(f"{i + 1}. ❌ {label}: you said {session.answers[i].response}, answer **{question.answer}**")
    return "\n".join(lines)


def results_prompt(session: QuizSession) -> str:
    """The results for the orchestrator, starting with the marker that ends the quiz."""
    total = len(session.quiz.questions)
    lines = [
        f"{FINISHED.format(session.id)} Quiz '{session.quiz.title}': {session.score} of {total} correct, "
        f"{len(session.answers)} answered."
    ]
    for i, question in enumerate(session.quiz.questions):
        if i < len(session.answers):
            given = session.answers[i]
            result = f"answered {given.response!r}, {'correct' if given.correct else 'wrong'}"
        else:
            result = "not answered"
        subject = f"{question.prompt} [{question.word}]" if question.word else question.prompt
        lines.append(f"{i + 1}. ({question.kind}) {_short(subject, 160)} | answer: {question.answer} | {result}")
    return "\n".join(lines)
