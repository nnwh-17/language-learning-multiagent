# This file turns an AnalysisResult into a file you can import into Anki.
# There is NO LLM in here: it's plain Python, so it's fast, free, and easy
# to test with fake data.
 
import csv
import html
from pathlib import Path
 
from llma.models.analysis import AnalysisResult, GrammarPoint, VocabItem
from llma.models.cards import AnkiCard
 
 
def _e(text: str) -> str:
    """Escape HTML special characters (<, >, &).
 
    We tell Anki the file contains HTML (so <br> line breaks work), which
    means any stray "<" in the text would be treated as a tag unless escaped.
    """
    return html.escape(text)
 
 
def vocab_to_card(item: VocabItem) -> AnkiCard:
    """Front: the word. Back: reading + meaning."""
    tags = ["vocab"]
    # Only add a JLPT tag if the model gave one (it can be None).
    if item.jlpt_level:
        tags.append(item.jlpt_level)
 
    return AnkiCard(
        front=_e(item.word),
        back=f"{_e(item.reading)}<br>{_e(item.meaning)}",
        tags=tags,
    )
 
 
def grammar_to_card(point: GrammarPoint) -> AnkiCard:
    """Front: the pattern. Back: explanation + the example from the text."""
    return AnkiCard(
        front=_e(point.pattern),
        back=f"{_e(point.explanation)}<br><br>Example: {_e(point.example_from_text)}",
        tags=["grammar"],
    )
 
 
def build_cards(analysis: AnalysisResult) -> list[AnkiCard]:
    """Convert everything in the analysis into a flat list of cards."""
    cards = [vocab_to_card(v) for v in analysis.vocab]
    cards += [grammar_to_card(g) for g in analysis.grammar]
    return cards
 
 
def write_anki_file(cards: list[AnkiCard], path: str | Path) -> Path:
    """Write cards to a tab-separated text file that Anki can import.
 
    In Anki: File > Import, pick this file. The first lines starting with "#"
    tell Anki how to read the file, so you don't have to set it up by hand.
    """
    path = Path(path)
    # Create the output folder if it doesn't exist yet.
    path.parent.mkdir(parents=True, exist_ok=True)
 
    # newline="" stops Python adding extra line breaks on Windows;
    # utf-8 is required for Japanese text.
    with path.open("w", encoding="utf-8", newline="") as f:
        # Header lines: tab-separated, fields contain HTML, tags are in column 3.
        f.write("#separator:tab\n")
        f.write("#html:true\n")
        f.write("#tags column:3\n")
 
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        for card in cards:
            # Anki expects tags separated by spaces in a single column.
            writer.writerow([card.front, card.back, " ".join(card.tags)])
 
    return path
 