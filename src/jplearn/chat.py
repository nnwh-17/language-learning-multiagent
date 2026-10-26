"""Run a terminal chat loop with the jplearn orchestrator.

This frontend maintains PydanticAI message history and asks the user to approve any
deferred Anki writes before continuing the same conversation.
"""

import asyncio
import sys

from pydantic_ai import DeferredToolRequests
from pydantic_ai.messages import ModelMessage

from jplearn.agents.orchestrator import describe_approval, orchestrator, tools_used


async def main() -> None:
    # Keep conversation history between turns so the tutor can use prior context.
    history: list[ModelMessage] = []
    print("Japanese tutor - type 'exit' to quit.\n")
    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if user_input.lower() in {"exit", "quit"}:
            break
        if not user_input:
            continue

        result = await orchestrator.run(user_input, message_history=history)
        # Tools marked requires_approval pause the run until the user decides
        while isinstance(result.output, DeferredToolRequests):
            approvals = {}
            for call in result.output.approvals:
                print(f"\n[approval needed]\n{describe_approval(call)}")
                approvals[call.tool_call_id] = input("approve? [y/N] ").strip().lower() == "y"
            result = await orchestrator.run(
                message_history=result.all_messages(),
                deferred_tool_results=result.output.build_results(approvals=approvals),
            )
        # Save the complete exchange, including any tool and approval messages.
        history = result.all_messages()

        if result.output.plan:
            print("\n[plan]")
            for i, step in enumerate(result.output.plan, 1):
                print(f"  {i}. {step}")
        if tools := tools_used(result.new_messages()):
            print(f"[tools] {', '.join(tools)}")
        print(f"\ntutor> {result.output.reply}\n")


if __name__ == "__main__":
    # Windows consoles default to a code page that can't print Japanese.
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
