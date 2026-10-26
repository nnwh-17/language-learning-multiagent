"""Settings from .env, file locations, and the shared LiteLLM-backed chat model.

Every environment variable the app reads is defined here, so other modules import the
value instead of calling ``os.getenv`` themselves. Agent modules call ``get_model()`` so
all specialists use the same configured provider and model name.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from openai.types import chat
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.litellm import LiteLLMProvider

load_dotenv()

# Files the app reads and writes, relative to the repository root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

# See .env.example for what each setting does.
MODEL_NAME = os.getenv("JPLEARN_MODEL", "claude-sonnet-5-5")
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


def get_model() -> OpenAIChatModel:
    """Model served through the LiteLLM proxy configured in .env."""
    return LiteLLMChatModel(
        MODEL_NAME,
        provider=LiteLLMProvider(
            api_base=os.getenv("LITELLM_API_BASE"),
            api_key=os.getenv("LITELLM_API_KEY"),
        ),
    )
