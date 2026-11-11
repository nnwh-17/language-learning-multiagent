"""Help with one chat message: an English translation, and simple notes on words the learner pastes.

The web UI's Translate and Words buttons on each tutor message call these agents. Neither
has tools: the word helper gets a word list of the pasted words from the tokenizer and
JMdict in its prompt, so readings and meanings are grounded in the dictionary.
"""

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from jplearn.activity import Observe
from jplearn.config import get_model
from jplearn.user_context import use_user_context


class LineTranslation(BaseModel):
    japanese: str = Field(description="One Japanese sentence or phrase from the message, copied exactly")
    english: str = Field(description="A natural English translation of it")


class MessageTranslation(BaseModel):
    lines: list[LineTranslation] = Field(description="Every Japanese sentence or phrase in the message, in order, each once")


class WordNote(BaseModel):
    word: str = Field(description="The word as it appears in the message")
    reading: str = Field(description="Its reading in hiragana; '' if it is already kana")
    meaning: str = Field(description="A short English meaning, a few words")
    here: str = Field(
        description="What it means or does in this message, in one or two plain sentences; "
        "if it is conjugated, name the dictionary form and what the ending adds"
    )
    example: str = Field(description="One very short, easy Japanese example sentence using it")
    example_english: str = Field(description="The example in English")


class WordHelp(BaseModel):
    notes: list[WordNote]


TRANSLATE_INSTRUCTIONS = """\
You translate the Japanese in one message from a Japanese tutor app for an English-speaking
learner. The message is often English with Japanese examples in it, or a Japanese text.

- List every Japanese sentence or phrase in the message, in order, each once, with a natural
  English translation. Copy the Japanese exactly.
- Skip text that is already English, romaji, and readings in brackets.
- Translate the meaning naturally, not word for word.
"""

WORDS_INSTRUCTIONS = """\
You explain words from one message of a Japanese tutor app to an English-speaking learner,
simply. You get the message, the words they pasted, and a word list of those words from a
tokenizer and dictionary.

- Write one note per word worth explaining. If they pasted a phrase, split it into its words;
  skip particles and endings unless they are what the learner pasted.
- Base readings and meanings on the word list; use the message to pick the right sense.
- Keep it simple, for a beginner (around JLPT N5-N4 unless their context says otherwise):
  `here` in at most two short sentences, no grammar jargon beyond 'dictionary form' and the
  name of a common ending (〜ます, 〜た, 〜て, 〜ない).
"""

message_translator = Agent(
    get_model(),
    output_type=MessageTranslation,
    instructions=TRANSLATE_INSTRUCTIONS,
    capabilities=[Observe("message_help")],
)
use_user_context(message_translator, "message_help")

word_helper = Agent(
    get_model(),
    output_type=WordHelp,
    instructions=WORDS_INSTRUCTIONS,
    capabilities=[Observe("message_help")],
)
use_user_context(word_helper, "message_help")


def words_prompt(message: str, words: str, word_list: str) -> str:
    """The word helper's input: the message, what the learner pasted, and its dictionary word list."""
    return (
        f"Message:\n{message}\n\n"
        f"Words the learner wants explained: {words}\n\n"
        f"Word list (tokenizer + JMdict):\n{word_list or '(nothing found)'}"
    )
