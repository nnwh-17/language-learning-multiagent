"""Load model settings and create the shared LiteLLM-backed chat model.

Agent modules call ``get_model()`` so all specialists use the same configured provider
and model name.
"""

import os

from dotenv import load_dotenv
from openai.types import chat
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.litellm import LiteLLMProvider

load_dotenv()

# Use the configured model name, falling back to the project default.
MODEL_NAME = os.getenv("JPLEARN_MODEL", "claude-sonnet-5-5")


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
    # Keep API credentials and the proxy URL in environment configuration, not code.
    return LiteLLMChatModel(
        MODEL_NAME,
        provider=LiteLLMProvider(
            api_base=os.getenv("LITELLM_API_BASE"),
            api_key=os.getenv("LITELLM_API_KEY"),
        ),
    )
