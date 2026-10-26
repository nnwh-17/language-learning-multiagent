# jplearn

## Setup

Requires Python 3.12+ and access to a LiteLLM proxy.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e .
copy .env.example .env   # then fill in the LITELLM_* values
```

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
python scripts/healthcheck.py          # imports, API key, tokenizer
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
    researcher.py    finds Japanese reading material on the web
  tokenizer.py       SudachiPy wrapper (readings, dictionary forms, POS)
  dictionary.py      JMdict lookups from data/jmdict.sqlite
  anki.py            Anki MCP server toolsets
  user_context.py    saved learner preferences (data/context.json) added to agent instructions
  architecture.py    the agent/tool diagram in the web UI's side panel
  activity.py        live activity tracking for that panel and the log
  log_view.py        renders the activity log
  web.py, theme.py   Gradio web UI and its styling
  chat.py            terminal UI
```

Anything that writes to Anki is an orchestrator tool with `requires_approval=True`, so both
UIs pause and ask the user first.

### Adding an agent

1. Create `agents/<name>.py` with an `Agent(get_model(), ..., capabilities=[Observe("<id>")])`
   and call `use_user_context(agent, "<id>")`.
2. Give the orchestrator a tool that runs it, and describe that tool in the orchestrator's
   `INSTRUCTIONS`.
3. Add a `Node("<id>", ...)` to `architecture.py` with the same tool names as edges, and to
   `check_against_agents`. The preferences dropdown picks up new agents from there.
4. Run `python scripts/healthcheck.py`. It fails if the diagram and the agents' tools disagree.
