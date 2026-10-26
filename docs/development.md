# Development

How to check changes and what to do when something breaks. There is no unit-test suite; the
scripts below are smoke tests against the real tokenizer, dictionary, model and Anki.

## Checks

| Command | Needs | What it checks |
|---|---|---|
| `python scripts/healthcheck.py` | — | Imports, provider settings, tokenizer, JMdict, and that the Agents diagram matches the agents' tools |
| `python scripts/healthcheck.py --live` | LLM access | Also one real model call |
| `python scripts/test_analyzer.py ["文"]` | LLM access | Tokenizer output, the Analyzer, and that the orchestrator delegates to it |
| `python scripts/test_anki_mcp.py` | Anki open | Anki MCP server starts and the flashcard tools exist (read-only) |
| `python scripts/test_anki_mcp.py --write --agent` | Anki open, LLM | Also adds and deletes a test note, and an agent using the Anki tools |
| `python scripts/test_flashcards.py` | Anki open, LLM | Drafting cards and the approval request; rejects, so nothing is written |
| `python scripts/test_flashcards.py --write` | Anki open, LLM | Approves, checks the cards are in Anki, then deletes them |

Scripts that write to Anki use a separate `jplearn-test` deck. Scripts that call the model
cost a little each run.

Add `-v` to the health check to print full tracebacks.

## After changing…

- **An agent's tools, or adding an agent:** update [architecture.py](../src/jplearn/architecture.py)
  to match, then run the health check (see [agents.md](agents.md#adding-an-agent)).
- **Prompts or output models:** run the matching smoke test, or try a few messages in the
  web UI with the **Agents** panel open to watch which tools are called.
- **Anything about approvals or Anki writes:** run `test_flashcards.py` in both modes.
- **Provider or model settings:** `healthcheck.py --live`.

## Running the app

```powershell
python -m jplearn.web    # web UI at http://127.0.0.1:7860
python -m jplearn.chat   # terminal chat
```

Use `-m` so Python treats the files as part of the `jplearn` package. Set
`GRADIO_SERVER_PORT` to use another port. The web UI doesn't reload on code changes; stop it
with `Ctrl+C` and start it again.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `UnicodeEncodeError: 'charmap' codec…` | Windows console code page. The scripts and terminal chat switch stdout to UTF-8 themselves; for your own scripts, add `sys.stdout.reconfigure(encoding="utf-8")` or set `PYTHONIOENCODING=utf-8` |
| `Dictionary not built` | Run `python scripts/setup_dictionary.py` |
| `npx not found` | Install Node.js 22.12+ |
| Anki tools fail or time out | Anki must be open with AnkiConnect installed. The first start downloads the MCP server via `npx` and can take a minute. Details in `anki-mcp.log` |
| `TypeError: Cannot instantiate typing.Union` | `anthropic` 2.x is installed; run `pip install -e .` to restore the pinned 1.x |
| `architecture diagram matches agents` fails | An agent's tools changed without updating `architecture.py`; the message lists both sides |
| Example sentences for a grammar pattern fail | The output check only recognises words. Ask the Explainer instead |
| A reply doesn't stream | The model output didn't parse as `{plan, reply}` JSON; see `stream_reply()` in `orchestrator.py` |

## Code conventions

- **Settings and paths** live in `config.py`; don't call `os.getenv` elsewhere.
- **Each agent module** starts with its output models and `INSTRUCTIONS`, then the `Agent`,
  then its tools.
- **Grounding:** tools that touch the tokenizer, JMdict or Anki wrap the work in
  `with track("<node id>"):` so it shows in the Agents panel.
- **Anki writes** happen only in orchestrator tools with `requires_approval=True`.
- **Docstrings** on tools and `Field` descriptions on output models are read by the model,
  so write them for the model as well as for people.
