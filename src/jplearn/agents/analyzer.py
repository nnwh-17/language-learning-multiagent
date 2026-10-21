from pydantic import BaseModel, Field
from pydantic_ai import Agent

from jplearn.activity import Observe, track
from jplearn.config import get_model
from jplearn.dictionary import lookup
from jplearn.tokenizer import Token, tokenize

# Parts of speech worth a dictionary lookup (particles/auxiliaries are grammar, not vocab)
LOOKUP_POS = {
    "noun", "pronoun", "verb", "i-adjective", "na-adjective", "adverb",
    "pre-noun adjectival", "conjunction", "interjection",
}


class TokenWithMeaning(Token):
    dictionary_meanings: list[str] = Field(
        default=[], description="JMdict meanings of the dictionary form, most common sense first"
    )


class Word(BaseModel):
    surface: str = Field(description="The word as it appears in the text")
    reading: str = Field(description="Hiragana reading of the surface form")
    dictionary_form: str
    dictionary_reading: str
    part_of_speech: str
    meaning: str = Field(description="Short English meaning in this context")
    note: str | None = Field(
        default=None, description="Conjugation or usage note, e.g. 'polite past of 見る'"
    )


class GrammarPoint(BaseModel):
    pattern: str = Field(description="The grammar pattern, e.g. 〜なければならない")
    meaning: str
    explanation: str = Field(description="How it is used in this text, 1-2 sentences")


class Breakdown(BaseModel):
    text: str
    translation: str
    words: list[Word] = Field(description="Content words and particles, in order. Merge auxiliaries into their verb.")
    grammar_points: list[GrammarPoint]


INSTRUCTIONS = """\
You break down Japanese text for an English-speaking learner.

Always call `tokenize_japanese` first. Use its readings, dictionary forms and parts of speech
rather than guessing. Base each word's `meaning` on its `dictionary_meanings` (JMdict),
picking the sense that fits the context; only fall back to your own knowledge when it is
empty (e.g. names). The tokenizer splits conjugations into pieces (e.g. 食べ + たかっ + た);
in `words`, merge a verb/adjective with its auxiliaries into one entry (食べたかった) and
explain the pieces in `note`. Grammar patterns that span several tokens
(e.g. 〜なければならない, 〜ている) go in `grammar_points`.
"""

analyzer = Agent(
    get_model(),
    output_type=Breakdown,
    instructions=INSTRUCTIONS,
    capabilities=[Observe("analyzer")],
)


@analyzer.tool_plain
def tokenize_japanese(text: str) -> list[TokenWithMeaning]:
    """Split Japanese text into tokens with hiragana reading, dictionary form (lemma),
    part of speech, conjugation form and JMdict meanings of content words."""
    with track("tokenizer"):
        tokenized = tokenize(text)
    tokens = []
    with track("jmdict"):
        for t in tokenized:
            meanings = []
            if t.pos in LOOKUP_POS and (entries := lookup(t.lemma, t.lemma_reading, max_entries=1)):
                meanings = ["; ".join(s.meanings) for s in entries[0].senses]
            tokens.append(TokenWithMeaning(**t.model_dump(), dictionary_meanings=meanings))
    return tokens
