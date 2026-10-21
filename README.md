# language-learning-multiagent
 
A multi-agent Japanese learning tool built with PydanticAI. Paste in Japanese text and it extracts vocab and grammar, generates new example sentences.
 
## Prerequisites
 
- Python 3.10 or newer
- An API key for your model provider (Anthropic, OpenAI or Gemini)
- Optional: [uv](https://docs.astral.sh/uv/) for faster installs
## Setup
 
1. Create and activate a virtual environment:
```bash
   python -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
```
 
2. Install dependencies:
```bash
   pip install -r requirements.txt
```
 
   With uv instead: `uv venv && uv pip install -r requirements.txt`
 
3. Add your API key. Create a `.env` file in the project root:
```
   ANTHROPIC_API_KEY=your_key_here
```
 
   Or use `OPENAI_API_KEY` / `GEMINI_API_KEY` for another provider. Do not commit this file.
 
4. Run the health check:
```bash
   python healthcheck.py
```
 
   Every line should print `[ OK ]`. To test a different model, set `HEALTHCHECK_MODEL`, for example `HEALTHCHECK_MODEL=openai:gpt-5 python healthcheck.py`.
 
## Troubleshooting
 
| Problem | Fix |
|---|---|
| `Cannot import pydantic-ai` | Activate your virtual environment, then rerun the install step |
| `No API key set` | Export the key in your shell, or check your `.env` file |
| `MCP support missing` | `pip install "pydantic-ai[mcp]"` |
| Live call fails with "model not found" | Check your provider's current model names and set `HEALTHCHECK_MODEL` |
 