"""Anki MCP server (https://github.com/ankimcp/anki-mcp-server) as a PydanticAI toolset.

Needs Anki desktop running with the AnkiConnect add-on (code 2055492159) and Node.js.
"""

import os
import shutil
from pathlib import Path

from dotenv import load_dotenv
from fastmcp.client.transports import StdioTransport
from pydantic_ai.mcp import MCPToolset

load_dotenv()

ANKI_MCP_PACKAGE = "@ankimcp/anki-mcp-server@0.27.0"
ANKI_CONNECT_URL = os.getenv("ANKI_CONNECT_URL", "http://localhost:8765")
# The server logs a lot to stderr; keep it out of the chat
LOG_FILE = Path(__file__).resolve().parents[2] / "anki-mcp.log"

# The server exposes ~50 tools; only show agents the ones they need.
FLASHCARD_TOOLS = {
    "listDecks",
    "createDeck",
    "modelNames",
    "modelFieldNames",
    "findNotes",
    "notesInfo",
    "addNote",
    "addNotes",
    "updateNoteFields",
    "addTags",
}


def anki_toolset(read_only: bool = False) -> MCPToolset:
    """Launch the Anki MCP server over stdio. Use it as `async with toolset:` or pass to an Agent."""
    npx = shutil.which("npx")
    if npx is None:
        raise RuntimeError("npx not found - install Node.js 22.12+")
    env = {**os.environ, "ANKI_CONNECT_URL": ANKI_CONNECT_URL}
    if read_only:
        env["READ_ONLY"] = "true"
    transport = StdioTransport(
        command=npx, args=["-y", ANKI_MCP_PACKAGE, "--stdio"], env=env, log_file=LOG_FILE
    )
    # First run downloads the npm package, so allow a generous start-up time
    return MCPToolset(transport, id="anki", init_timeout=120)


def flashcard_toolset(read_only: bool = False, tools: set[str] = FLASHCARD_TOOLS):
    """Anki toolset limited to deck/note tools."""
    return anki_toolset(read_only).filtered(lambda ctx, tool_def: tool_def.name in tools)
