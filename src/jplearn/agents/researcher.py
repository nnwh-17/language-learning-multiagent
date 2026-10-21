from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.common_tools.duckduckgo import duckduckgo_search_tool
from pydantic_ai.common_tools.web_fetch import web_fetch_tool

from jplearn.activity import Observe, track
from jplearn.config import get_model
from jplearn.user_context import use_user_context

_search = duckduckgo_search_tool(max_results=5).function
_fetch = web_fetch_tool(max_content_length=8_000, timeout=20).function


class Material(BaseModel):
    found: bool = Field(description="False if nothing suitable was found")
    title: str
    url: str
    japanese_text: str = Field(
        description="Japanese passage to study (at most ~600 characters), copied from the page"
    )
    level: str = Field(description="Rough difficulty, e.g. 'beginner (N5-N4)', 'intermediate (N3)'")
    summary: str = Field(description="One or two sentences in English about the material")
    notes: str | None = Field(default=None, description="Caveats, e.g. why nothing was found")


INSTRUCTIONS = """\
You find Japanese reading material on the web for an English-speaking learner.

1. Search with `search_web`. Searching in Japanese usually works better
   (e.g. "料理 ニュース やさしい日本語").
2. Open the most promising result with `fetch_page` and check it really contains Japanese
   text that fits the request. Prefer learner-friendly sources (NHK やさしいことばニュース,
   Wikipedia ja, Watanoc, Tadoku) when the user wants something easy.
3. Return one `Material` with a passage copied from the page (at most ~600 characters).

Limits: at most 3 searches and 3 page fetches. If a tool reports an error, try once more
differently, then return found=false with the reason in `notes`.

Song lyrics are copyrighted: never return more than 4 lines of lyrics. Give the page URL
so the user can read the rest there.
"""

researcher = Agent(
    get_model(),
    output_type=Material,
    instructions=INSTRUCTIONS,
    capabilities=[Observe("researcher")],
)
use_user_context(researcher, "researcher")


@researcher.tool_plain
async def search_web(query: str) -> list[dict] | str:
    """Search the web (DuckDuckGo). Returns title, url (`href`) and snippet of each result."""
    with track("web_search"):
        try:
            return await _search(query)
        except Exception as e:  # network/DNS problems shouldn't end the run
            return f"Search failed: {type(e).__name__}: {e}"


@researcher.tool_plain
async def fetch_page(url: str) -> dict | str:
    """Fetch a web page and return its main content as markdown (truncated)."""
    with track("web_fetch"):
        try:
            return await _fetch(url)
        except Exception as e:
            return f"Fetch failed: {type(e).__name__}: {e}"
