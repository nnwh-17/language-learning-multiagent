"""Smoke-test Anki MCP connectivity and its deck/note operations.

Requires Anki desktop open with AnkiConnect. Default checks are read-only.
--write  adds a test note to a "jplearn-test" deck, reads it back, then deletes it
--agent  asks an LLM agent (with the Anki tools) what decks you have

The shared toolsets and allowed tool names come from ``jplearn.anki``.
"""

import asyncio
import sys

from jplearn.anki import FLASHCARD_TOOLS, LOG_FILE, anki_toolset, flashcard_toolset

TEST_DECK = "jplearn-test"


def step(name: str, detail: object = "") -> None:
    print(f"[OK] {name}  {detail}")


async def read_checks(ts) -> None:
    """Verify expected tools and read basic collection metadata without changes."""
    tools = {t.name for t in await ts.list_tools()}
    step("server started", f"{len(tools)} tools")
    missing = FLASHCARD_TOOLS - tools
    assert not missing, f"tools missing from server: {missing}"
    step("flashcard tools present", ", ".join(sorted(FLASHCARD_TOOLS)))

    decks = await ts.direct_call_tool("listDecks", {})
    step("listDecks", [d["name"] for d in decks["decks"]])
    models = await ts.direct_call_tool("modelNames", {})
    step("modelNames", models)
    fields = await ts.direct_call_tool("modelFieldNames", {"modelName": "Basic"})
    step("modelFieldNames(Basic)", fields)


async def write_checks(ts) -> None:
    """Create, read, and delete one disposable note in the test deck."""
    await ts.direct_call_tool("createDeck", {"deckName": TEST_DECK})
    step("createDeck", TEST_DECK)

    added = await ts.direct_call_tool(
        "addNote",
        {
            "deckName": TEST_DECK,
            "modelName": "Basic",
            "fields": {"Front": "食べる", "Back": "たべる - to eat"},
            "tags": ["jplearn-test"],
            "allowDuplicate": True,
        },
    )
    step("addNote", added)

    found = await ts.direct_call_tool("findNotes", {"query": f'"deck:{TEST_DECK}"'})
    note_ids = found["noteIds"]
    assert note_ids, f"note not found: {found}"
    info = await ts.direct_call_tool("notesInfo", {"notes": note_ids})
    step("findNotes + notesInfo", info["notes"][0]["fields"]["Front"]["value"])

    await ts.direct_call_tool("deleteNotes", {"notes": note_ids, "confirmDeletion": True})
    step("deleteNotes", f"removed {len(note_ids)} (empty '{TEST_DECK}' deck left behind)")


async def agent_check() -> None:
    from pydantic_ai import Agent

    from jplearn.config import get_model

    agent = Agent(
        get_model(),
        toolsets=[flashcard_toolset(read_only=True)],
        instructions="You help manage the user's Anki collection. Use the tools.",
    )
    result = await agent.run("What Anki decks do I have? Reply in one line.")
    tool_calls = [p.tool_name for m in result.all_messages() for p in m.parts if p.part_kind == "tool-call"]
    step("agent via MCP", f"called {tool_calls} -> {result.output.strip()}")


async def main() -> None:
    # Keep the MCP process scoped to the checks; write mode is explicitly opt-in.
    async with anki_toolset(read_only="--write" not in sys.argv) as ts:
        await read_checks(ts)
        if "--write" in sys.argv:
            await write_checks(ts)
    if "--agent" in sys.argv:
        await agent_check()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"[FAIL] {type(e).__name__}: {e}")
        print(f"Is Anki open with AnkiConnect? Server log: {LOG_FILE}")
        sys.exit(1)
