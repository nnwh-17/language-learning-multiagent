from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry

from jplearn.activity import Observe, log, track
from jplearn.config import get_model
from jplearn.dictionary import DictEntry, lookup
from jplearn.tokenizer import tokenize
from jplearn.user_context import use_user_context


class Example(BaseModel):
    japanese: str
    reading: str = Field(description="The whole sentence in hiragana")
    translation: str
    target_form: str = Field(description="How the word appears and the form's name, e.g. '鳴りました (polite past)'")
    sense: str = Field(description="Which meaning of the word this sentence shows, e.g. 'to ring'")
    note: str | None = Field(default=None, description="Short usage note, e.g. 'intransitive, so が not を'")


class WordExamples(BaseModel):
    word: str = Field(description="Dictionary form used, in its usual spelling (e.g. 鳴る)")
    reading: str
    examples: list[Example]


class ExampleSet(BaseModel):
    words: list[WordExamples]


INSTRUCTIONS = """\
You write example sentences for an English-speaking learner of Japanese.

For each word you are given:
1. Call `lookup_word` to get its dictionary meanings. If a kana word matches several
   entries (e.g. なる = 成る "become" / 鳴る "ring"), use the most common one unless the
   request says otherwise, and set `word` to its usual spelling.
2. Write the requested number of sentences (default 3). Cover different meanings first,
   then vary the form (polite/plain, past, negative, te-form) and show typical
   collocations (e.g. 電話が鳴る).
3. Keep sentences short and natural, with vocabulary and grammar at the learner's level
   (see their context if given; otherwise beginner, N5-N4).

Each sentence must contain the word itself (any conjugation), not a synonym.
"""

examples_agent = Agent(
    get_model(),
    output_type=ExampleSet,
    instructions=INSTRUCTIONS,
    capabilities=[Observe("examples")],
    retries={"output": 2},  # room for the output check to send sentences back
)
use_user_context(examples_agent, "examples")


@examples_agent.tool_plain
def lookup_word(word: str, reading: str | None = None) -> list[DictEntry]:
    """Look up a Japanese word in JMdict. `reading` (hiragana) optionally narrows homographs."""
    with track("jmdict"):
        entries = lookup(word, reading)
        if not entries and word.endswith("する"):
            # JMdict lists 勉強する under the noun 勉強 (marked "suru verb")
            entries = lookup(word[:-2], reading[:-2] if reading and reading.endswith("する") else None)
        return entries


def uses_word(sentence: str, word: str) -> bool:
    """Whether the tokenizer finds `word` (in any conjugation) in `sentence`. A kana `word`
    also matches its kanji spelling (なる matches 鳴りました), a kanji one only itself."""
    if word in sentence:
        return True
    tokens = tokenize(sentence)
    if word.endswith("する") and len(word) > 2:
        # Noun + する verbs are split by the tokenizer: 勉強しています = 勉強 + し(する) + ...
        stem = word[:-2]
        return any(t.lemma == stem and n.lemma == "する" for t, n in zip(tokens, tokens[1:]))
    return any(word in (t.lemma, t.lemma_reading) for t in tokens)


@examples_agent.output_validator
def check_examples(output: ExampleSet) -> ExampleSet:
    """Reject sentences that don't actually contain the target word, so the model fixes them."""
    with track("tokenizer"):
        problems = [
            f"'{ex.japanese}' does not use {w.word}"
            for w in output.words
            for ex in w.examples
            if not uses_word(ex.japanese, w.word)
        ]
    problems += [f"no sentences for {w.word}" for w in output.words if not w.examples]
    if problems:
        log("info", "Output check failed, asking for a fix", "; ".join(problems))
        raise ModelRetry("Fix these sentences so each contains the target word: " + "; ".join(problems))
    return output
