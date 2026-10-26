"""Write short quizzes the learner answers interactively in the web UI.

The orchestrator calls this agent through ``start_quiz``; the quiz goes to the UI's quiz
panel (not into the model's context), and ``grade`` checks each answer there. Questions are
checked before they reach the learner: choices must contain the answer, and readings must
match the tokenizer.
"""

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry

from jplearn.activity import Observe, log, track
from jplearn.config import get_model
from jplearn.dictionary import DictEntry, lookup
from jplearn.kana import romaji_to_hiragana
from jplearn.tokenizer import to_hiragana, tokenize
from jplearn.user_context import use_user_context

BLANK = "＿＿"


class Question(BaseModel):
    kind: Literal["choice", "reading", "fill_in"] = Field(
        description="choice: pick one option; reading: type the kana reading of `word`; fill_in: type what goes in the blank"
    )
    prompt: str = Field(
        description=f"The question shown to the learner. For fill_in, a Japanese sentence with {BLANK} for the gap "
        "plus its English meaning. Never include the answer or a reading of the tested word."
    )
    word: str | None = Field(default=None, description="For reading: the Japanese word (with kanji) to read")
    options: list[str] = Field(default=[], description="For choice: 3-4 short options, exactly one correct")
    answer: str = Field(description="For choice: the correct option, word for word. Otherwise: the answer in kana")
    also_accept: list[str] = Field(default=[], description="Other answers that are also correct, in kana")
    explanation: str = Field(description="1-2 sentences shown after answering: why this is the answer")


class Quiz(BaseModel):
    title: str = Field(description="Short topic name, e.g. 'N5 verbs' or 'は vs が'")
    questions: list[Question] = Field(min_length=1, max_length=10)


INSTRUCTIONS = f"""\
You write short quizzes for an English-speaking learner of Japanese. The learner answers
them one at a time in an app, which marks typed answers automatically.

- Default to 5 questions at the learner's level (see their context; otherwise beginner,
  N5-N4), unless the request says otherwise. Mix question kinds where the topic allows.
- choice: for meanings, grammar and usage. Distractors should be plausible (same part of
  speech, commonly confused), with exactly one correct option.
- reading: give the word in `word` and ask for its reading. Only for words with kanji.
- fill_in: one short sentence with {BLANK} where a particle or a conjugated word goes,
  followed by its English meaning. Put every correct answer in `answer`/`also_accept`.
- Typed answers are kana only; the app also accepts romaji.
- Use `lookup_word` to check meanings you test. Never give away the answer in the prompt
  (no readings in brackets for the tested word).
- Explanations are short and teach something: the rule, or why a distractor is wrong.
"""

quiz_agent = Agent(
    get_model(),
    output_type=Quiz,
    instructions=INSTRUCTIONS,
    capabilities=[Observe("quiz")],
    retries={"output": 2},  # room for the output check to send questions back
)
use_user_context(quiz_agent, "quiz")


@quiz_agent.tool_plain
def lookup_word(word: str, reading: str | None = None) -> list[DictEntry]:
    """Look up a Japanese word in JMdict. `reading` (hiragana) optionally narrows homographs."""
    with track("jmdict"):
        return lookup(word, reading)


def reading_of(word: str) -> str:
    """The tokenizer's hiragana reading of a word."""
    return to_hiragana("".join(token.reading for token in tokenize(word)))


def question_problems(question: Question) -> list[str]:
    """Why a question can't be shown as it is (empty when it is fine)."""
    if question.kind == "choice":
        if not 2 <= len(question.options) <= 5:
            return [f"'{question.prompt}' needs 2-5 options"]
        if len(set(question.options)) != len(question.options):
            return [f"'{question.prompt}' has duplicate options"]
        if question.answer not in question.options:
            return [f"the answer to '{question.prompt}' must be one of its options, word for word"]
        return []
    if question.kind == "reading":
        if not question.word:
            return [f"reading question '{question.prompt}' needs `word`"]
        expected = reading_of(question.word)
        if expected not in {normalize_answer(a) for a in [question.answer, *question.also_accept]}:
            return [f"the reading of {question.word} is {expected}, not {question.answer}"]
        if expected in question.prompt:
            return [f"'{question.prompt}' gives away the reading"]
        return []
    if BLANK not in question.prompt:
        return [f"fill_in question '{question.prompt}' needs {BLANK} where the answer goes"]
    return []


@quiz_agent.output_validator
def check_quiz(quiz: Quiz) -> Quiz:
    """Send back questions that can't be answered or marked correctly."""
    with track("tokenizer"):
        problems = [problem for question in quiz.questions for problem in question_problems(question)]
    if problems:
        log("info", "Quiz check failed, asking for a fix", "; ".join(problems))
        raise ModelRetry("Fix these questions: " + "; ".join(problems))
    return quiz


_IGNORED = re.compile(r"[\s。、.,!?！？「」\"']")
_KANJI = re.compile(r"[一-鿿々]")
_SPOKEN_PARTICLES = {"は": "わ", "へ": "え", "を": "お"}  # how they sound, so romaji "wa" counts


def normalize_answer(text: str) -> str:
    """Hiragana with spacing and punctuation removed. Romaji is converted, and so is kanji
    (via the tokenizer's reading), so 見ています, みています and mite imasu all match."""
    text = unicodedata.normalize("NFKC", text).strip().lower()
    if re.fullmatch(r"[a-z' -]+", text):
        text = romaji_to_hiragana(text.replace(" ", ""))
    elif _KANJI.search(text):
        text = reading_of(text)
    return _IGNORED.sub("", to_hiragana(text))


def grade(question: Question, response: str) -> bool:
    """Whether the learner's response to `question` is correct."""
    if question.kind == "choice":
        return response == question.answer
    given = normalize_answer(response)
    accepted = {normalize_answer(a) for a in [question.answer, *question.also_accept]}
    accepted |= {_SPOKEN_PARTICLES[a] for a in accepted if a in _SPOKEN_PARTICLES}
    return bool(given) and given in accepted
