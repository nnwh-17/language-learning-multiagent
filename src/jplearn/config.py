"""Settings from .env, file locations, and the shared chat model.

Every environment variable the app reads is defined here, so other modules import the
value instead of calling ``os.getenv`` themselves. Agent modules call ``get_model()`` so
all specialists use the same configured provider and model name.

Two providers are supported, chosen with ``JPLEARN_PROVIDER``:
- ``litellm`` (default): an OpenAI-compatible LiteLLM proxy (LITELLM_API_BASE / LITELLM_API_KEY)
- ``anthropic``: the Claude API directly (ANTHROPIC_API_KEY, or an ``ant auth login`` profile)
"""

import os
from pathlib import Path
from typing import Literal

from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from openai.types import chat
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelSettings
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.litellm import LiteLLMProvider

load_dotenv()

# Files the app reads and writes, relative to the repository root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

# See .env.example for what each setting does.
PROVIDER: Literal["litellm", "anthropic"] = os.getenv("JPLEARN_PROVIDER", "litellm").lower()  # type: ignore[assignment]
MODEL_NAME = os.getenv("JPLEARN_MODEL", "claude-sonnet-5-5")
EFFORT = os.getenv("JPLEARN_EFFORT") or None  # Claude API only; unset = the model's default
DEFAULT_DECK = os.getenv("JPLEARN_DECK", "jplearn")
ANKI_CONNECT_URL = os.getenv("ANKI_CONNECT_URL", "http://localhost:8765")


class LiteLLMChatModel(OpenAIChatModel):
    """OpenAIChatModel that tolerates LiteLLM's extra response fields.

    The proxy adds a `metadata` field (e.g. `weight_versions` as a list) that doesn't
    match OpenAI's `dict[str, str]` schema, so drop it before validation.
    """

    def _validate_completion(self, response: chat.ChatCompletion):
        response.metadata = None
        return super()._validate_completion(response)


# Models that accept Anthropic's server-side refusal fallback: if a safety classifier
# declines a request, the API re-runs it on a suitable model inside the same call.
SERVER_FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}


def get_model() -> Model:
    """The chat model for the provider configured in .env."""
    if PROVIDER == "anthropic":
        return _claude_model()
    if PROVIDER != "litellm":
        raise RuntimeError(f"JPLEARN_PROVIDER must be 'litellm' or 'anthropic', not {PROVIDER!r}")
    return LiteLLMChatModel(
        MODEL_NAME,
        provider=LiteLLMProvider(
            api_base=os.getenv("LITELLM_API_BASE"),
            api_key=os.getenv("LITELLM_API_KEY"),
        ),
    )


def _claude_model() -> AnthropicModel:
    settings = AnthropicModelSettings()
    if EFFORT:
        settings["anthropic_effort"] = EFFORT
    if MODEL_NAME in SERVER_FALLBACK_MODELS:
        settings["anthropic_betas"] = ["server-side-fallback-2026-07-01"]
        settings["extra_body"] = {"fallbacks": "default"}
    # The SDK client finds credentials itself: ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN,
    # or a profile from `ant auth login`.
    provider = AnthropicProvider(anthropic_client=AsyncAnthropic())
    return AnthropicModel(MODEL_NAME, provider=provider, settings=settings)
