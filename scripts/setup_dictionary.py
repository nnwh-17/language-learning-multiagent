"""Downloads JMdict (English, via jmdict-simplified) and builds data/jmdict.sqlite.

Run once: python scripts/setup_dictionary.py   (re-run any time to update)
"""

import io
import json
import sqlite3
import urllib.request
import zipfile

from jplearn.dictionary import DB_PATH

RELEASES = "https://api.github.com/repos/scriptin/jmdict-simplified/releases/latest"


def download() -> dict:
    with urllib.request.urlopen(RELEASES) as r:
        release = json.load(r)
    asset = next(
        a for a in release["assets"]
        if a["name"].startswith("jmdict-eng-3") and a["name"].endswith(".json.zip")
    )
    print(f"Downloading {asset['name']} ({asset['size'] // 1024 // 1024} MB)...")
    with urllib.request.urlopen(asset["browser_download_url"]) as r:
        data = r.read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return json.loads(z.read(z.namelist()[0]))


def build(jmdict: dict) -> None:
    DB_PATH.parent.mkdir(exist_ok=True)
    tmp = DB_PATH.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
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
    DB_PATH.unlink(missing_ok=True)
    tmp.rename(DB_PATH)
    print(f"Built {DB_PATH} with {len(jmdict['words'])} entries (JMdict {jmdict['dictDate']})")


if __name__ == "__main__":
    build(download())
