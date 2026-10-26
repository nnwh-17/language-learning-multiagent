"""Download English JMdict data and build the local SQLite database.

``jplearn.dictionary`` builds and reads the generated ``data/jmdict.sqlite`` file. Run this
script once during setup or again to refresh the source data.
"""

import io
import json
import sys
import urllib.request
import zipfile

from jplearn.dictionary import DB_PATH, build_database

# Windows consoles default to a code page that can't print Japanese.
sys.stdout.reconfigure(encoding="utf-8")

RELEASES = "https://api.github.com/repos/scriptin/jmdict-simplified/releases/latest"


def download() -> dict:
    """Fetch the latest English JMdict release asset and parse its JSON contents."""
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


if __name__ == "__main__":
    jmdict = download()
    build_database(jmdict)
    print(f"Built {DB_PATH} with {len(jmdict['words'])} entries (JMdict {jmdict['dictDate']})")
