# Configuration

All settings are environment variables, normally set in `.env` (copy
[.env.example](../.env.example)). They are read in one place,
[config.py](../src/jplearn/config.py); other modules import the values from there.

## Settings

| Variable | Default | What it does |
|---|---|---|
| `JPLEARN_PROVIDER` | `litellm` | Where the LLM comes from: `litellm` or `anthropic` |
| `JPLEARN_MODEL` | `claude-sonnet-5-5` | Model for every agent. A Claude model ID, or for LiteLLM the name configured on the proxy |
| `LITELLM_API_BASE` | — | LiteLLM proxy URL (provider `litellm`) |
| `LITELLM_API_KEY` | — | LiteLLM proxy key (provider `litellm`) |
| `ANTHROPIC_API_KEY` | — | Claude API key (provider `anthropic`). Optional if you use `ant auth login` |
| `JPLEARN_EFFORT` | model default | Claude only: `low`, `medium`, `high`, `xhigh` or `max` |
| `JPLEARN_DECK` | `jplearn` | Anki deck for new cards when the user doesn't name one |
| `ANKI_CONNECT_URL` | `http://localhost:8765` | AnkiConnect address, passed to the Anki MCP server |
| `PYDANTIC_AI_NO_BANNER` | — | Set to `1` to hide PydanticAI's startup banner |

`python scripts/healthcheck.py` checks the provider settings and reports which provider and
model are active.

## Providers

### LiteLLM proxy (`JPLEARN_PROVIDER=litellm`)

An OpenAI-compatible proxy. `JPLEARN_MODEL` is whatever name the proxy uses for the model.

`LiteLLMChatModel` drops the `metadata` field the proxy adds to responses, because it doesn't
match OpenAI's schema and would fail validation.

### Claude API (`JPLEARN_PROVIDER=anthropic`)

Calls Anthropic directly through PydanticAI's `AnthropicModel` and the official `anthropic`
SDK.

- **Credentials:** the SDK client finds them itself: `ANTHROPIC_API_KEY`,
  `ANTHROPIC_AUTH_TOKEN`, or a profile from `ant auth login`.
- **Model:** set `JPLEARN_MODEL` to a Claude model ID. `claude-opus-5-5` is the most
  capable; `claude-sonnet-5-5` is faster and cheaper.
- **Effort:** `JPLEARN_EFFORT` sets how much the model thinks before answering. Lower is
  faster and cheaper. Unset uses the model's default (`medium` on Opus 5.5, `high` on
  Sonnet 5.5). It applies to every agent.
- **Refusal fallback:** for the models in `SERVER_FALLBACK_MODELS` (Fable 5.1, Opus 5.5,
  Opus 5, Sonnet 5.5), requests opt into Anthropic's server-side fallback. If a safety filter
  declines a request, the API re-runs it on a suitable model inside the same call. The
  fallback model's answer is billed at that model's rates. Empty the set to turn it off.
- **Structured output:** on Claude, PydanticAI returns `{plan, reply}` as native JSON text
  instead of a tool call. `stream_reply()` handles both forms; keep that in mind if you
  change how replies are parsed.
- **SDK version:** `pyproject.toml` pins `anthropic<2`. PydanticAI 2.58 is built against the
  1.x SDK, and 2.x breaks it (`TypeError: Cannot instantiate typing.Union`). Lift the pin
  only together with a PydanticAI release that supports 2.x.

## Files

| Path | What it is | In git? |
|---|---|---|
| `data/jmdict.sqlite` | JMdict dictionary, built by `scripts/setup_dictionary.py` (~170 MB) | No |
| `data/context.json` | The learner's saved preferences, edited in the web UI | No |
| `data/chats/*.json` | Saved web chats, one file each; delete a file to delete the chat | No |
| `anki-mcp.log` | Output of the Anki MCP server, kept out of the chat | No |
| `.env` | Your settings and keys | No |

Paths are defined in `config.py` (`PROJECT_ROOT`, `DATA_DIR`).
