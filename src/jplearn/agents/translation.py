"""Check the learner's own translation of a Japanese text and break down the mistakes.

The web UI's Read & translate tab calls this agent, the one model call in that tab. It gets
a word list of the text from the tokenizer and JMdict, so the review is grounded in checked
readings and meanings. Each mistake quotes the part of the text it is about, which the tab
then highlights for study.
"""

from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from jplearn.activity import Observe
from jplearn.config import get_model
from jplearn.user_context import use_user_context


class Mistake(BaseModel):
    japanese: str = Field(
        description="The word or short phrase of the original text that was misunderstood, copied exactly from it"
    )
    you_wrote: str = Field(description="What the learner wrote for that part, quoted from their translation; '' if they left it out")
    problem: str = Field(description="What went wrong and why, in one or two plain sentences")
    better: str = Field(description="A correct English rendering of that part")
    kind: Literal["vocab", "grammar", "nuance", "missing"]


class TranslationReview(BaseModel):
    verdict: Literal["spot on", "mostly right", "partly right", "off track"]
    summary: str = Field(description="One or two encouraging sentences on how they did overall")
    reference: str = Field(description="A natural English translation of the whole text")
    got_right: list[str] = Field(default=[], description="Things they understood well, a few words each")
    mistakes: list[Mistake] = Field(default=[], description="Real misunderstandings, in text order")


INSTRUCTIONS = """\
You check an English-speaking learner's own translation of a Japanese text. You get the
text, a word list of it from a tokenizer and dictionary, the parts the learner highlighted
as not knowing, and their translation.

- Judge meaning, not wording. Free or natural translations are fine; so are English typos
  and style. Only list real misunderstandings: wrong meaning, wrong grammar (tense,
  negation, who does what to whom, conditionals, ...), lost nuance that changes the
  message, or parts left out.
- Base meanings on the word list, not your own guesses.
- In `japanese`, copy the shortest part of the text that the mistake is about (one word or
  a short phrase), character for character, so it can be highlighted.
- Keep `problem` short and teach the point (e.g. "〜てしまう adds regret or completion,
  not 'try'").
- `got_right` should be specific, so the learner knows what to trust.
"""

translation_checker = Agent(
    get_model(),
    output_type=TranslationReview,
    instructions=INSTRUCTIONS,
    capabilities=[Observe("translation")],
)
use_user_context(translation_checker, "translation")


def review_prompt(text: str, word_list: str, highlighted: list[str], translation: str) -> str:
    """The checker's input: the text, its word list, what the learner highlighted, and their attempt."""
    return (
        f"Japanese text:\n{text}\n\n"
        f"Word list (tokenizer + JMdict):\n{word_list}\n\n"
        f"Highlighted by the learner as unknown: {', '.join(highlighted) or 'nothing'}\n\n"
        f"The learner's translation:\n{translation}"
    )
