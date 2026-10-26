"""Build and look up the local JMdict SQLite database.

``scripts/setup_dictionary.py`` downloads JMdict and calls ``build_database``; the agents use
``lookup`` to ground meanings in dictionary entries.
"""

import json
import sqlite3
from functools import cache
from pathlib import Path

from pydantic import BaseModel

from jplearn.config import DATA_DIR

DB_PATH = DATA_DIR / "jmdict.sqlite"


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


def build_database(jmdict: dict, path: Path = DB_PATH) -> None:
    """Write a jmdict-simplified JSON export to `path` as an indexed SQLite database.

    Builds a temporary file first, so an interrupted build never replaces a working database.
    """
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    # Store entries as source JSON and index every kanji/kana form for exact lookup.
    db.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE entries (id INTEGER PRIMARY KEY, common INTEGER, data TEXT);
        CREATE TABLE forms (text TEXT, entry_id INTEGER);
        CREATE INDEX forms_text ON forms (text);
    """)
    db.execute("INSERT INTO meta VALUES ('version', ?)", (jmdict["dictDate"],))
    db.execute("INSERT INTO meta VALUES ('tags', ?)", (json.dumps(jmdict["tags"], ensure_ascii=False),))
    for word in jmdict["words"]:
        forms = word["kanji"] + word["kana"]
        common = any(f["common"] for f in forms)
        db.execute(
            "INSERT INTO entries VALUES (?, ?, ?)",
            (int(word["id"]), common, json.dumps(word, ensure_ascii=False)),
        )
        db.executemany(
            "INSERT INTO forms VALUES (?, ?)", [(f["text"], int(word["id"])) for f in forms]
        )
    db.commit()
    db.close()
    path.unlink(missing_ok=True)
    tmp.rename(path)


@cache
def _db() -> sqlite3.Connection:
    # Reuse one connection for the process; fail clearly if setup has not been run.
    if not DB_PATH.exists():
        raise RuntimeError("Dictionary not built - run: python scripts/setup_dictionary.py")
    return sqlite3.connect(DB_PATH, check_same_thread=False)


@cache
def _tags() -> dict[str, str]:
    (tags,) = _db().execute("SELECT value FROM meta WHERE key = 'tags'").fetchone()
    return json.loads(tags)


def _entry(word: dict, common: bool, max_senses: int) -> DictEntry:
    # Convert the source JSON and compact JMdict tags into typed app models.
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
    entries = _lookup_exact(word, reading, max_entries, max_senses)
    if not entries and word.endswith("する") and len(word) > 2:
        # JMdict lists 勉強する under the noun 勉強 (marked "suru verb")
        stem_reading = reading[:-2] if reading and reading.endswith("する") else None
        entries = _lookup_exact(word[:-2], stem_reading, max_entries, max_senses)
    return entries


def _lookup_exact(
    word: str, reading: str | None, max_entries: int, max_senses: int
) -> list[DictEntry]:
    # Search indexed kanji/kana forms, then prefer the requested reading when available.
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
