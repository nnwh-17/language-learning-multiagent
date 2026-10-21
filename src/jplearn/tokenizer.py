"""Tokenize Japanese into readings, dictionary forms, and English part-of-speech labels.

The analyzer and example generator use this shared SudachiPy wrapper to ground model
outputs and validate generated sentences.
"""

import threading
from functools import cache

from pydantic import BaseModel
from sudachipy import Dictionary, SplitMode

POS_EN = {
    "名詞": "noun",
    "代名詞": "pronoun",
    "動詞": "verb",
    "形容詞": "i-adjective",
    "形状詞": "na-adjective",
    "連体詞": "pre-noun adjectival",
    "副詞": "adverb",
    "接続詞": "conjunction",
    "感動詞": "interjection",
    "助詞": "particle",
    "助動詞": "auxiliary verb",
    "接頭辞": "prefix",
    "接尾辞": "suffix",
}

# Conjugation forms, matched by prefix (Sudachi adds suffixes like "-一般")
FORM_EN = {
    "未然形": "irrealis (negative/passive stem)",
    "連用形": "continuative (masu/te stem)",
    "終止形": "plain/dictionary form",
    "連体形": "attributive (before a noun)",
    "仮定形": "hypothetical (ba stem)",
    "命令形": "imperative",
    "意志推量形": "volitional",
    "語幹": "stem",
}

SKIP_POS = {"補助記号", "空白"}  # punctuation, whitespace


class Token(BaseModel):
    surface: str
    reading: str
    lemma: str
    lemma_reading: str
    pos: str
    pos_detail: str
    conjugation: str | None = None


@cache
def _dictionary() -> Dictionary:
    # Loading Sudachi's system dictionary is expensive, so share it process-wide.
    return Dictionary()  # slow to load, so shared


_local = threading.local()


def _tokenizer():
    """A Sudachi tokenizer can't be used by two threads at once, and PydanticAI runs sync
    tools in worker threads (sometimes in parallel), so each thread gets its own."""
    if not hasattr(_local, "tokenizer"):
        _local.tokenizer = _dictionary().tokenizer()
    return _local.tokenizer


def to_hiragana(katakana: str) -> str:
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in katakana)


def _reading_of(surface: str, katakana_reading: str) -> str:
    # Katakana words (loanwords like ベル) keep their katakana reading
    return surface if surface == katakana_reading else to_hiragana(katakana_reading)


def _reading(text: str) -> str:
    return "".join(
        _reading_of(m.surface(), m.reading_form()) for m in _tokenizer().tokenize(text, SplitMode.C)
    )


def tokenize(text: str) -> list[Token]:
    """Split Japanese text into words with reading, dictionary form and part of speech."""
    tokens = []
    # Convert Sudachi's token metadata into stable, English-labelled model input.
    for m in _tokenizer().tokenize(text, SplitMode.C):
        pos = m.part_of_speech()
        if pos[0] in SKIP_POS:
            continue
        lemma = m.dictionary_form()
        form = next((en for jp, en in FORM_EN.items() if pos[5].startswith(jp)), None)
        tokens.append(
            Token(
                surface=m.surface(),
                reading=_reading_of(m.surface(), m.reading_form()),
                lemma=lemma,
                lemma_reading=_reading(lemma),
                pos=POS_EN.get(pos[0], pos[0]),
                pos_detail=",".join(p for p in pos[:5] if p != "*"),
                conjugation=form,
            )
        )
    return tokens
