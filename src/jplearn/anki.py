"""Provide Anki MCP toolsets for the flashcard agents and orchestrator.

The server runs over stdio and talks to AnkiConnect. ``flashcards.py`` uses a filtered,
read-only toolset to check for existing cards; write operations use the full toolset and
are exposed by the orchestrator behind user approval.

Requires Anki desktop with the AnkiConnect add-on (code 2055492159) and Node.js.
"""

import os
import shutil

from fastmcp.client.transports import StdioTransport
from pydantic_ai.mcp import MCPToolset, ProcessToolCallback
from pydantic_ai.toolsets import FilteredToolset

from jplearn.config import ANKI_CONNECT_URL, PROJECT_ROOT

ANKI_MCP_PACKAGE = "@ankimcp/anki-mcp-server@0.27.0"
# Keep verbose server output out of the chat.
LOG_FILE = PROJECT_ROOT / "anki-mcp.log"

# Restrict the Anki API surface to the deck and note operations used by this app.
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


def anki_toolset(
    read_only: bool = False, process_tool_call: ProcessToolCallback | None = None
) -> MCPToolset:
    """Launch the Anki MCP server; use it as an async context manager or agent toolset."""
    npx = shutil.which("npx")
    if npx is None:
        raise RuntimeError("npx not found - install Node.js 22.12+")

    # Pass connection settings to the child process and enable server-side read-only mode.
    env = {**os.environ, "ANKI_CONNECT_URL": ANKI_CONNECT_URL}
    if read_only:
        env["READ_ONLY"] = "true"

    # npx installs the pinned server package on first use; allow time for that startup.
    transport = StdioTransport(
        command=npx, args=["-y", ANKI_MCP_PACKAGE, "--stdio"], env=env, log_file=LOG_FILE
    )
    return MCPToolset(
        transport, id="anki", init_timeout=120, process_tool_call=process_tool_call
    )


def flashcard_toolset(
    read_only: bool = False,
    tools: set[str] = FLASHCARD_TOOLS,
    process_tool_call: ProcessToolCallback | None = None,
) -> FilteredToolset:
    """Build an Anki toolset exposing only the selected deck/note operations."""
    return anki_toolset(read_only, process_tool_call).filtered(
        lambda ctx, tool_def: tool_def.name in tools
    )
