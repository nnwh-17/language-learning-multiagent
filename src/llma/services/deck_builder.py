import html
from pathlib import Path
 
from llma.models.analysis import AnalysisResult
from llma.models.examples import ExampleSentence
from llma.services.card_builder import build_cards, write_anki_file
 
 
def build_deck(
    analysis: AnalysisResult,
    examples: dict[str, list[ExampleSentence]],
    path: str | Path,
) -> tuple[Path, int]:
    """Build cards, add example sentences to the back, write the Anki file."""
    cards = build_cards(analysis)
 
    # build_cards returns vocab cards first, then grammar, in analysis order
    keys = [v.word for v in analysis.vocab] + [g.pattern for g in analysis.grammar]
 
    for card, key in zip(cards, keys, strict=True):
        for ex in examples.get(key, []):
            e = html.escape
            card.back += f"<br><br>{e(ex.japanese)}<br>{e(ex.reading)}<br>{e(ex.english)}"
 
    return write_anki_file(cards, path), len(cards)