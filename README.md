# jplearn

## Setup

Requires Python 3.12+ and access to a LiteLLM proxy.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e .
copy .env.example .env   # then fill in the LITELLM_* values
```

## Check everything works

```powershell
python scripts/healthcheck.py          # imports, API key, tokenizer
python scripts/healthcheck.py --live   # also makes one real LLM call
```

## Run

```powershell
python -m jplearn.chat
```
