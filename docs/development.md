# Development

How to check changes and what to do when something breaks.

## Tests

```powershell
pip install -e ".[dev]"   # once, adds pytest
pytest                    # ~15 s, offline and free
```

The tests in [tests/](../tests/) never call a real model, Anki or the web, so they run the
same on any machine and in CI (GitHub Actions runs them on every push and pull request):

- **No LLM:** [conftest.py](../tests/conftest.py) sets `ALLOW_MODEL_REQUESTS = False`, so an
  agent a test forgets to replace fails instead of spending money. Tests replace agents'
  models with `agent.override(model=...)`.
- **Scripted models:** [scripted.py](../tests/scripted.py) builds fake models that do exactly
  what a test says, step by step: `call(tool, args)`, `answer(plan, reply)`, or the streamed
  versions for the web UI. PydanticAI's `TestModel` fills in generated values when the exact
  output doesn't matter.
- **Tiny dictionary:** a four-word JMdict database is built with `build_database()` for the
  test session, instead of the 170 MB real one.
- **Throwaway preferences and chats:** each test gets its own empty `context.json` and chats
  folder.
- **Fake Anki:** `FakeAnki` in [test_agents.py](../tests/test_agents.py) answers the few MCP
  calls `flashcards.py` makes.

| File | Covers |
|---|---|
| `test_language_tools.py` | Tokenizer, dictionary lookups (incl. する verbs), the example-sentence check |
| `test_app_state.py` | Saved preferences, activity tracking, the agents diagram matches the code |
| `test_agents.py` | Routing to specialists, user context in instructions, approve/reject, Anki write helpers |
| `test_web.py` | A full web turn: streaming, locked composer, replying instead of approving, errors, furigana |
| `test_conversations.py` | Saving and reopening chats, resuming history, a pending approval surviving a reload |
| `test_quiz.py` | Romaji input, marking, the question check, the quiz panel, a whole quiz played through the web UI |

When you add a feature, add a test next to the closest existing one. For a new agent, copy
`test_orchestrator_delegates_to_explainer_with_users_context`.

## Smoke tests

The scripts below check the real tokenizer, dictionary, model and Anki together. Run them
before a release, or after changing prompts or provider settings; they are slower and the
ones that call the model cost a little.

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

- **Anything:** `pytest`.
- **An agent's tools, or adding an agent:** update [architecture.py](../src/jplearn/architecture.py)
  to match; `pytest` and the health check both fail until they agree (see
  [agents.md](agents.md#adding-an-agent)).
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
