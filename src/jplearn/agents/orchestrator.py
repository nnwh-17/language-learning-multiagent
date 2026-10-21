from pydantic import BaseModel, Field
from pydantic_ai import Agent

from jplearn.config import get_model


class OrchestratorReply(BaseModel):
    plan: list[str] = Field(
        description="Short step-by-step plan for handling the request. Empty for small talk."
    )
    reply: str = Field(description="The message shown to the user.")


INSTRUCTIONS = """\
You are the orchestrator AI agent of a Japanese-learning multi-agent system. The user is an English
speaker learning Japanese.

For every message:
1. Work out what the user wants (explain grammar, break down a sentence, quiz them,
   make flashcards, find material, casual practice, ...).
2. Write a short plan of the steps you would take.
3. Answer the user directly.

No specialist agents or tools are connected yet, but do not carry out the plan yourself.
When you write Japanese, add furigana for kanji the first time it appears, e.g. 食(た)べる.
Keep replies concise.
"""

orchestrator = Agent(
    get_model(),
    output_type=OrchestratorReply,
    instructions=INSTRUCTIONS,
)
