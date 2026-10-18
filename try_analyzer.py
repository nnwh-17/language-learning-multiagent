"""Scratch script: run the analyzer on a sample text and print the result.
 
Usage (from the project root):
    python try_analyzer.py                       # uses samples/sample_text.txt
    python try_analyzer.py path/to/your_text.txt
"""
 
import sys
from pathlib import Path
 
from dotenv import load_dotenv
 
# Read the .env file (if there is one) and put its values, like the API key, into the environment.
load_dotenv()
 
# The code lives in src/, which Python doesn't search by default.
# This adds it to the import path so "from llma..." works without having to install the project as a package.
sys.path.insert(0, str(Path(__file__).parent / "src"))
 
# the "noqa: E402" comment is there (it silences a linter warning about imports not being at the top of the file).
from llma.agents.analyzer import analyzer_agent  # noqa: E402
 
 
def main() -> None:
    # Use the file given on the command line, or fall back to the sample.
    # sys.argv[0] is the script name, so sys.argv[1] is the first argument.
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("samples/sample_text.txt")
    # Japanese text needs UTF-8 to be read correctly on every operating system.
    text = path.read_text(encoding="utf-8")
 
    print(f"Input ({path}):\n{text}\n")
 
    # sends the text to the model and waits for the answer.
    result = analyzer_agent.run_sync(text)
    
    # result.output is a validated AnalysisResult object, not raw text,
    # so we can use it like any Python object (analysis.vocab, v.word, ...).
    analysis = result.output
 
    # Print each vocabulary item on one line.
    print(f"--- Vocab ({len(analysis.vocab)}) ---")
    for v in analysis.vocab:
        # jlpt_level can be None, so show "?" when it's missing.
        level = v.jlpt_level or "?"
        print(f"{v.word}  [{v.reading}]  {v.meaning}  ({level})")
 
    # Print each grammar point, plus the sentence it came from.
    print(f"\n--- Grammar ({len(analysis.grammar)}) ---")
    for g in analysis.grammar:
        print(f"{g.pattern}: {g.explanation}")
        print(f"    from text: {g.example_from_text}")
 
    # Token usage shows roughly what the call cost. Useful to watch as you
    # experiment with longer texts and longer prompts.
    usage = result.usage
    print(f"\nTokens: {usage.input_tokens} in / {usage.output_tokens} out")
 
 
# Only run main() when this file is executed directly (python try_analyzer.py),
# not when it is imported by another file.
if __name__ == "__main__":
    main()