"""Terminal chat with the orchestrator. Run: python -m jplearn.chat"""

import asyncio

from pydantic_ai.messages import ModelMessage

from jplearn.agents.orchestrator import orchestrator


async def main() -> None:
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
        history = result.all_messages()

        if result.output.plan:
            print("\n[plan]")
            for i, step in enumerate(result.output.plan, 1):
                print(f"  {i}. {step}")
        print(f"\ntutor> {result.output.reply}\n")


if __name__ == "__main__":
    asyncio.run(main())
