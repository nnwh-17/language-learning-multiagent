"""Japanese text file in -> Anki import file out.
 
Usage:
    python main.py                          # samples/sample_text.txt -> output/deck.txt
    python main.py my_text.txt out/deck.txt
"""
 
import sys
from pathlib import Path
 
from dotenv import load_dotenv
 
load_dotenv()  # load API key from .env (before the agent is created)
sys.path.insert(0, str(Path(__file__).parent / "src"))  # make src/ importable
 
from llma.agents.analyzer import analyzer_agent  # noqa: E402
from llma.services.card_builder import build_cards, write_anki_file  # noqa: E402
 
 
def main() -> None:
    # Optional args: input path, output path
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("samples/sample_text.txt")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("output/deck.txt")
 
    text = src.read_text(encoding="utf-8")
 
    # 1. LLM step: extract vocab and grammar
    analysis = analyzer_agent.run_sync(text).output
 
    # 2. Plain code step: build cards and write the Anki file
    cards = build_cards(analysis)
    write_anki_file(cards, out)
 
    print(f"{len(analysis.vocab)} vocab + {len(analysis.grammar)} grammar -> {len(cards)} cards")
    print(f"Saved to {out}")
 
 
if __name__ == "__main__":
    main()