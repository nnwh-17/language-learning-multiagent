"""Shared test setup: no real LLM calls, a tiny JMdict database, a throwaway preferences file.

Every test runs offline. Agents are driven by PydanticAI's `TestModel` / `FunctionModel`
through `agent.override(model=...)`, so tests are fast, free and deterministic.
"""

import os

# Settings must be in place before jplearn.config is imported (it reads them at import).
os.environ.update(JPLEARN_PROVIDER="litellm", LITELLM_API_BASE="http://test.invalid", LITELLM_API_KEY="test")

import pytest  # noqa: E402
from pydantic_ai import models  # noqa: E402

from jplearn import dictionary, user_context  # noqa: E402

# Any agent a test forgets to override fails loudly instead of calling the real model.
models.ALLOW_MODEL_REQUESTS = False


def _word(id: int, kanji: list[str], kana: list[str], glosses: list[str], pos: list[str], common: bool) -> dict:
    """One entry in jmdict-simplified's JSON format."""
    return {
        "id": str(id),
        "kanji": [{"text": k, "common": common} for k in kanji],
        "kana": [{"text": k, "common": common} for k in kana],
        "sense": [{"gloss": [{"text": g} for g in glosses], "partOfSpeech": pos, "misc": [], "info": []}],
    }


TINY_JMDICT = {
    "dictDate": "test",
    "tags": {"v1": "Ichidan verb", "v5r": "Godan verb with 'ru' ending", "n": "noun", "vs": "suru verb"},
    "words": [
        _word(1, ["食べる"], ["たべる"], ["to eat"], ["v1"], common=True),
        _word(2, ["勉強"], ["べんきょう"], ["study"], ["n", "vs"], common=True),
        _word(3, ["成る"], ["なる"], ["to become"], ["v5r"], common=True),
        _word(4, ["鳴る"], ["なる"], ["to sound", "to ring"], ["v5r"], common=False),
    ],
}


@pytest.fixture(scope="session", autouse=True)
def tiny_dictionary(tmp_path_factory):
    """Point jplearn.dictionary at a four-word database built from TINY_JMDICT."""
    path = tmp_path_factory.mktemp("jmdict") / "jmdict.sqlite"
    dictionary.build_database(TINY_JMDICT, path)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(dictionary, "DB_PATH", path)
        dictionary._db.cache_clear()
        dictionary._tags.cache_clear()
        yield path
        dictionary._db().close()
        dictionary._db.cache_clear()
        dictionary._tags.cache_clear()


@pytest.fixture(autouse=True)
def preferences_file(tmp_path, monkeypatch):
    """Keep saved preferences in a temporary file, so tests never read or change the real one."""
    path = tmp_path / "context.json"
    monkeypatch.setattr(user_context, "CONTEXT_FILE", path)
    return path


@pytest.fixture
def anyio_backend():
    return "asyncio"
