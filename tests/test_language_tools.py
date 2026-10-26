"""The deterministic Japanese tools: tokenizer, dictionary, and the example sentence check."""

import pytest
from pydantic_ai import ModelRetry

from jplearn.agents.examples import Example, ExampleSet, WordExamples, check_examples, uses_word
from jplearn.dictionary import lookup
from jplearn.tokenizer import to_hiragana, tokenize

# --- tokenizer ---


def test_tokenize_gives_lemma_reading_and_pos():
    tokens = tokenize("ご飯を食べたかった。")
    verb = next(t for t in tokens if t.surface == "食べ")
    assert (verb.lemma, verb.lemma_reading, verb.pos) == ("食べる", "たべる", "verb")
    assert verb.conjugation == "continuative (masu/te stem)"


def test_tokenize_skips_punctuation():
    assert all(t.surface not in "、。" for t in tokenize("昨日、行きました。"))


def test_katakana_words_keep_katakana_reading():
    (bell, *_) = tokenize("ベルが鳴る")
    assert bell.reading == "ベル"


def test_to_hiragana_only_changes_katakana():
    assert to_hiragana("タベル abc 漢字") == "たべる abc 漢字"


# --- dictionary ---


def test_lookup_exact_word():
    (entry,) = lookup("食べる")
    assert entry.senses[0].meanings == ["to eat"]
    assert entry.senses[0].part_of_speech == ["Ichidan verb"]  # tag codes expanded


def test_lookup_puts_common_words_first():
    assert [e.kanji for e in lookup("なる")] == [["成る"], ["鳴る"]]


def test_lookup_by_kanji_spelling_finds_only_that_entry():
    assert [e.kanji for e in lookup("鳴る", "なる")] == [["鳴る"]]


def test_lookup_suru_verb_falls_back_to_noun():
    (entry,) = lookup("勉強する", "べんきょうする")
    assert entry.kanji == ["勉強"]
    assert "suru verb" in entry.senses[0].part_of_speech


def test_lookup_unknown_word_is_empty():
    assert lookup("存在しない") == []
    assert lookup("する") == []  # bare する must not fall back to an empty stem


# --- example sentence check ---


@pytest.mark.parametrize(
    ("sentence", "word"),
    [
        ("電話が鳴りました。", "鳴る"),  # conjugated
        ("電話が鳴りました。", "なる"),  # kana word matches its kanji spelling
        ("毎日勉強しています。", "勉強する"),  # noun + する split by the tokenizer
        ("ご飯を食べる。", "食べる"),  # plain substring
    ],
)
def test_uses_word_finds_target(sentence, word):
    assert uses_word(sentence, word)


def test_uses_word_rejects_synonym():
    assert not uses_word("ご飯を召し上がる。", "食べる")


def _examples(word: str, *sentences: str) -> ExampleSet:
    examples = [Example(japanese=s, reading="", translation="", target_form="", sense="") for s in sentences]
    return ExampleSet(words=[WordExamples(word=word, reading="", examples=examples)])


def test_check_examples_accepts_valid_output():
    output = _examples("鳴る", "電話が鳴りました。")
    assert check_examples(output) is output


def test_check_examples_sends_bad_sentences_back():
    with pytest.raises(ModelRetry, match="召し上がる"):
        check_examples(_examples("食べる", "ご飯を召し上がる。"))


def test_check_examples_rejects_word_without_sentences():
    with pytest.raises(ModelRetry, match="no sentences for 食べる"):
        check_examples(_examples("食べる"))
