# jplearn

A multi-agent Japanese tutor for English speakers. You chat with one agent, which plans each
request and hands parts of it to specialists: sentence breakdowns, explanations with
analogies, example sentences, interactive quizzes, reading material from the web, and Anki
flashcards. Japanese
facts come from a tokenizer (SudachiPy) and a local dictionary (JMdict) rather than the
model's memory, and nothing is written to Anki until you approve it.

## Documentation

- [Architecture](docs/architecture.md): how a message flows through the agents, approvals,
  live activity and streaming
- [Agents](docs/agents.md): what each agent does, and how to add one
- [Configuration](docs/configuration.md): every `.env` setting, LiteLLM vs the Claude API
- [Development](docs/development.md): smoke tests, troubleshooting, code conventions

## Setup

Requires Python 3.12+ and either access to a LiteLLM proxy or a Claude API key.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e .
copy .env.example .env   # then fill in the settings for your provider
```

Choose the LLM provider in `.env`:

- **LiteLLM proxy** (default): `JPLEARN_PROVIDER=litellm` plus `LITELLM_API_BASE` and `LITELLM_API_KEY`.
- **Claude API**: `JPLEARN_PROVIDER=anthropic` plus `ANTHROPIC_API_KEY` (or run `ant auth login`
  instead of setting a key). Optionally set `JPLEARN_EFFORT` (`low` to `max`) to trade answer
  depth for speed and cost.

`JPLEARN_MODEL` is the model for either provider, e.g. `claude-sonnet-5-5` or `claude-opus-5-5`.
All settings are listed in [docs/configuration.md](docs/configuration.md).

### Dictionary

```powershell
python scripts/setup_dictionary.py   # downloads JMdict, builds data/jmdict.sqlite (~170 MB)
```

### Anki

1. Install [Anki](https://apps.ankiweb.net/) desktop and [Node.js](https://nodejs.org/) 22.12+.
2. In Anki: Tools → Add-ons → Get Add-ons → code `2055492159` (AnkiConnect), then restart Anki.
3. Keep Anki open while using the app. The Anki MCP server is started automatically via `npx`.

## Check everything works

```powershell
pip install -e ".[dev]"; pytest       # offline tests, ~15 s (see docs/development.md)
python scripts/healthcheck.py          # imports, model settings, tokenizer
python scripts/healthcheck.py --live   # also makes one real LLM call
python scripts/test_analyzer.py        # tokenizer, analyzer agent, orchestrator -> analyzer
python scripts/test_anki_mcp.py        # Anki MCP server, read-only
python scripts/test_anki_mcp.py --write --agent   # also add/delete a test note, and an agent using the tools
python scripts/test_flashcards.py      # draft cards, reject the add (nothing written)
python scripts/test_flashcards.py --write   # approve, check cards in Anki, delete them
```

## Run

```powershell
python -m jplearn.web    # web chat at http://127.0.0.1:7860
python -m jplearn.chat   # terminal chat
```

## Project layout

```
src/jplearn/
  config.py          settings from .env, file paths, the shared LLM model
  agents/
    orchestrator.py  the agent you chat with; plans and delegates to the others
    analyzer.py      word-by-word breakdown (tokenizer + JMdict)
    flashcards.py    drafts Anki cards; also the Anki write helpers
    examples.py      example sentences, checked to contain each word
    explainer.py     explains concepts with analogies, comparisons and common mistakes
    researcher.py    finds Japanese reading material on the web
    quiz.py          writes quizzes and marks answers (kana, romaji or kanji)
  tokenizer.py       SudachiPy wrapper (readings, dictionary forms, POS)
  dictionary.py      JMdict lookups from data/jmdict.sqlite
  anki.py            Anki MCP server toolsets
  user_context.py    saved learner preferences (data/context.json) added to agent instructions
  conversations.py   saved web chats (data/chats/), reopened after a reload or restart
  architecture.py    the agent/tool diagram in the web UI's side panel
  activity.py        live activity tracking for that panel and the log
  log_view.py        renders the activity log
  quiz_view.py       the web UI's interactive quiz panel
  kana.py            romaji → hiragana, furigana rendering
  web.py, theme.py   Gradio web UI and its styling
  chat.py            terminal UI
```

To add an agent, follow [Adding an agent](docs/agents.md#adding-an-agent).
