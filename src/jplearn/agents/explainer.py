"""Explain Japanese concepts through analogies, comparisons and connections.

The orchestrator calls this agent for "why / how / what's the difference" questions about
grammar, vocabulary, nuance or culture. It grounds word meanings in JMdict and relates new
ideas to things the learner already knows.
"""

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from jplearn.activity import Observe, track
from jplearn.config import get_model
from jplearn.dictionary import DictEntry, lookup
from jplearn.user_context import use_user_context


class Analogy(BaseModel):
    comparison: str = Field(description="The analogy, e.g. 'は is like a spotlight on the topic'")
    limits: str = Field(description="Where the analogy breaks down, in one sentence")


class Related(BaseModel):
    item: str = Field(description="A related or easily confused item, e.g. が, or English 'the'")
    relation: str = Field(description="How it connects to or differs from the topic")


class ExampleLine(BaseModel):
    japanese: str
    translation: str
    point: str = Field(description="What this example shows about the topic")


class Explanation(BaseModel):
    topic: str
    core_idea: str = Field(description="The essence in one or two plain-English sentences")
    analogies: list[Analogy] = Field(description="One or two analogies, from everyday life or languages the learner knows")
    related: list[Related] = Field(description="Similar, contrasting or prerequisite items and how they relate")
    examples: list[ExampleLine] = Field(description="Two to four short examples, ideally minimal pairs")
    pitfalls: list[str] = Field(default=[], description="Common learner mistakes or misconceptions")
    check_question: str | None = Field(
        default=None, description="One quick question the learner can answer to test their understanding"
    )


INSTRUCTIONS = """\
You explain Japanese to an English-speaking learner so that it clicks, not just so that it
is correct.

1. Find the core idea: what the item does, in one or two plain sentences, without jargon.
2. Give one or two analogies, from everyday life or from languages the learner knows (see
   their context, e.g. Mandarin or Korean; otherwise English). Always say where the
   analogy breaks down.
3. Relate it to what the learner probably knows: similar or easily confused items (は/が,
   に/で, 〜ている/〜てある), the English it is often mistranslated as, and anything it
   builds on. Say how each one differs.
4. Show it with short examples at the learner's level (otherwise beginner, N5-N4).
   Minimal pairs that change only the item being explained work best.
5. List common mistakes, and end with one quick question to check understanding.

For questions about a word's meaning or nuance, call `lookup_word` first and base the
meaning on its JMdict senses. Don't invent etymologies or rules; if usage really varies or
is debated, say so.
"""

explainer = Agent(
    get_model(),
    output_type=Explanation,
    instructions=INSTRUCTIONS,
    capabilities=[Observe("explainer")],
)
use_user_context(explainer, "explainer")


@explainer.tool_plain
def lookup_word(word: str, reading: str | None = None) -> list[DictEntry]:
    """Look up a Japanese word in JMdict. `reading` (hiragana) optionally narrows homographs."""
    with track("jmdict"):
        return lookup(word, reading)
