"""Smoke-test flashcard drafting, approval handling, and Anki writes.

The flow covers orchestrator -> flashcard agent -> analyzer, then approval -> Anki.
Needs Anki open. Uses the "jplearn-test" deck.
--write  approves the add, checks the cards are in Anki, then deletes them
(default: rejects the add, so nothing is written)
"""

import asyncio
import sys

from pydantic_ai import DeferredToolRequests

from jplearn.agents.orchestrator import describe_approval, orchestrator, tools_used
from jplearn.anki import anki_toolset

# Windows consoles default to a code page that can't print Japanese.
sys.stdout.reconfigure(encoding="utf-8")

DECK = "jplearn-test"
TEXT = "ベルが鳴ったら、静かにしなければならない。"


async def main() -> None:
    # Draft a test batch and assert that the orchestrator pauses for approval.
    write = "--write" in sys.argv

    print("== orchestrator drafts cards")
    result = await orchestrator.run(f"Make flashcards from this sentence into the deck {DECK}: {TEXT}")
    print(f"  tools used: {tools_used(result.all_messages())}")
    assert isinstance(result.output, DeferredToolRequests), f"expected approval request, got {result.output}"
    (call,) = result.output.approvals
    assert call.tool_name == "add_flashcards"
    print(describe_approval(call))

    # Exercise either branch of the approval flow; writes are opt-in for safety.
    print(f"\n== user {'approves' if write else 'rejects'}")
    result = await orchestrator.run(
        message_history=result.all_messages(),
        deferred_tool_results=result.output.build_results(approve_all=write)
        if write
        else result.output.build_results(approvals={call.tool_call_id: False}),
    )
    print(f"  tutor> {result.output.reply}")

    async with anki_toolset() as anki:
        found = await anki.direct_call_tool("findNotes", {"query": f'"deck:{DECK}" tag:jplearn'})
        note_ids = found["noteIds"]
        if write:
            assert note_ids, "no cards were added"
            print(f"\n[OK] {len(note_ids)} cards in Anki - deleting them")
            await anki.direct_call_tool("deleteNotes", {"notes": note_ids, "confirmDeletion": True})
        else:
            assert not note_ids, f"cards were added despite rejection: {note_ids}"
            print("\n[OK] rejected - nothing added to Anki")


if __name__ == "__main__":
    asyncio.run(main())
