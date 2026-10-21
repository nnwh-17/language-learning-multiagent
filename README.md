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
```

## Run

```powershell
python -m jplearn.web    # web chat at http://127.0.0.1:7860
python -m jplearn.chat   # terminal chat
```
