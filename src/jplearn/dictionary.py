"""JMdict lookups. Build the database first: python scripts/setup_dictionary.py"""

import json
import sqlite3
from functools import cache
from pathlib import Path

from pydantic import BaseModel

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "jmdict.sqlite"


class Sense(BaseModel):
    meanings: list[str]
    part_of_speech: list[str]
    notes: list[str] = []  # usage notes, e.g. "usually written using kana alone"


class DictEntry(BaseModel):
    jmdict_id: int
    kanji: list[str]
    readings: list[str]
    common: bool
    senses: list[Sense]


@cache
def _db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise RuntimeError("Dictionary not built - run: python scripts/setup_dictionary.py")
    return sqlite3.connect(DB_PATH, check_same_thread=False)


@cache
def _tags() -> dict[str, str]:
    (tags,) = _db().execute("SELECT value FROM meta WHERE key = 'tags'").fetchone()
    return json.loads(tags)


def _entry(word: dict, common: bool, max_senses: int) -> DictEntry:
    tags = _tags()
    senses = [
        Sense(
            meanings=[g["text"] for g in s["gloss"]],
            part_of_speech=[tags.get(p, p) for p in s["partOfSpeech"]],
            notes=[tags.get(m, m) for m in s["misc"]] + s["info"],
        )
        for s in word["sense"][:max_senses]
    ]
    return DictEntry(
        jmdict_id=int(word["id"]),
        kanji=[k["text"] for k in word["kanji"]],
        readings=[k["text"] for k in word["kana"]],
        common=common,
        senses=senses,
    )


def lookup(
    word: str, reading: str | None = None, max_entries: int = 3, max_senses: int = 4
) -> list[DictEntry]:
    """Exact-match lookup on kanji or kana forms; common words first.

    If `reading` (hiragana) is given, entries with that reading are preferred.
    """
    rows = _db().execute(
        """SELECT DISTINCT e.data, e.common FROM forms f JOIN entries e ON e.id = f.entry_id
           WHERE f.text = ? ORDER BY e.common DESC, e.id LIMIT 30""",
        (word,),
    ).fetchall()
    words = [(json.loads(data), bool(common)) for data, common in rows]
    if reading:
        matching = [(w, c) for w, c in words if any(k["text"] == reading for k in w["kana"])]
        words = matching or words
    return [_entry(w, c, max_senses) for w, c in words[:max_entries]]
