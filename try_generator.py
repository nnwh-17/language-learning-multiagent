"""Scratch script: test the example generator on hand-written items.
 
Skips the analyzer, so you test one agent at a time.
Usage: python try_generator.py
"""
 
import asyncio
import sys
from pathlib import Path
 
from dotenv import load_dotenv
 
load_dotenv()  # load API key before the agent is created
sys.path.insert(0, str(Path(__file__).parent / "src"))  # make src/ importable
 
from llma.agents.example_generator import generate_all  # noqa: E402
from llma.models.analysis import AnalysisResult, GrammarPoint, VocabItem  # noqa: E402
 
# Fake analysis: edit these to try other words and patterns
analysis = AnalysisResult(
    vocab=[
        VocabItem(word="食べる", reading="たべる", meaning="to eat", jlpt_level="N5"),
        VocabItem(word="留学", reading="りゅうがく", meaning="studying abroad"),
    ],
    grammar=[
        GrammarPoint(
            pattern="～ながら",
            explanation="while doing (two actions at once)",
            example_from_text="コーヒーを飲みながら、話しました。",
        )
    ],
)
 
 
async def main() -> None:
    results = await generate_all(analysis, n=2)
    for key, examples in results.items():
        print(f"\n=== {key} ===")
        for ex in examples:
            print(f"{ex.japanese}\n  {ex.reading}\n  {ex.english}")
 
 
if __name__ == "__main__":
    asyncio.run(main())