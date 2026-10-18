# Defines the analyzer agent: it takes Japanese text and returns an AnalysisResult (vocab + grammar). It only DEFINES the agent.


import os

from pydantic_ai import Agent
# Agent: the core PydanticAI class. An agent bundles a model, a system
# prompt, an output type, and (optionally) tools.

from llma.models.analysis import AnalysisResult

DEFAULT_MODEL = "anthropic:claude-haiku-5-5"

# The system prompt tells the model its role and the rules to follow.
SYSTEM_PROMPT = """You are a Japanese language teacher helping a learner build flashcards from a text.
 
Given Japanese text, extract:
 
1. Vocabulary worth studying.
   - Use the dictionary form (食べました -> 食べる).
   - Give the reading in hiragana and a concise English meaning.
   - Skip particles, basic grammar words (です, ます, する), numbers and proper names.
   - Give a JLPT level only if you are confident, otherwise null.
 
2. Grammar points.
   - Give the pattern in its base form with a short English explanation.
   - Quote the exact fragment from the text that uses it.
   - Only include real grammar patterns, not single vocabulary words.
 
Do not invent content that is not in the text. Return at most 15 vocab items and 5 grammar points,
prioritising items that are most useful for a learner."""

def build_analyzer(model: str | None = None) -> Agent[None, AnalysisResult]:
    """Create an analyzer agent.
 
    Wrapping the construction in a function lets us build agents with
    different models later (e.g. in tests, or to compare models).
    The type hint Agent[None, AnalysisResult] means: no dependencies (None),
    and the agent's output is an AnalysisResult.
    """
    return Agent(
        # Model priority: the argument, then the JP_ANKI_MODEL environment
        # variable, then the default above.
        model or os.environ.get("JP_ANKI_MODEL", DEFAULT_MODEL),
        # output_type makes the model return structured data matching this
        # class, and PydanticAI validates it before handing it to us.
        output_type=AnalysisResult,
        system_prompt=SYSTEM_PROMPT,
    )
    
# A ready-to-use instance, so other files can just import it.
analyzer_agent = build_analyzer()