"""Chat with the llma supervisor.
 
Usage: python chat.py
Type @path/to/file.txt to send a text file's contents. Type quit to exit.
"""
 
import asyncio
import sys
from pathlib import Path
 
from dotenv import load_dotenv
 
load_dotenv()  # load API key before agents are created
sys.path.insert(0, str(Path(__file__).parent / "src"))  # make src/ importable
 
from llma.agents.supervisor import build_supervisor  # noqa: E402
from llma.deps import State  # noqa: E402
 
# --- MCP goes here later ---
# from pydantic_ai.mcp import MCPServerStdio
# dictionary = MCPServerStdio("python", args=["-m", "llma.mcp_servers.dictionary_server"])
# supervisor = build_supervisor(toolsets=[dictionary])
supervisor = build_supervisor()
 
 
def expand_file(user: str) -> str:
    """'@file.txt' -> the file's contents, so multi-line text is easy to send."""
    path = Path(user[1:].strip())
    try:
        return f"Here is Japanese text from {path.name}:\n\n{path.read_text(encoding='utf-8')}"
    except OSError as e:
        print(f"Can't read {path}: {e}")
        return ""
 
 
async def main() -> None:
    state = State()  # shared data (analysis, examples) across turns
    history = []  # chat memory
 
    # "async with" starts any MCP servers and stops them on exit
    async with supervisor:
        print("llma ready. Paste Japanese text or type @file.txt. 'quit' to exit.")
        while True:
            try:
                user = input("\nyou> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if user.lower() in {"quit", "exit"}:
                break
            if user.startswith("@"):
                user = expand_file(user)
            if not user:
                continue
 
            result = await supervisor.run(user, deps=state, message_history=history)
            history = result.all_messages()  # pass back next turn so it remembers
            print(f"\nllma> {result.output}")
 
 
if __name__ == "__main__":
    asyncio.run(main())