"""Small kana helpers for showing and checking Japanese text in the UI.

``romaji_to_hiragana`` lets quiz answers be typed without a Japanese keyboard, and
``with_furigana`` shows readings written as 漢字(かんじ) above the kanji.
"""

import re

VOWELS = "aiueo"
_ROWS = {
    "": "あいうえお", "k": "かきくけこ", "g": "がぎぐげご", "s": "さしすせそ", "z": "ざじずぜぞ",
    "t": "たちつてと", "d": "だぢづでど", "n": "なにぬねの", "h": "はひふへほ", "b": "ばびぶべぼ",
    "p": "ぱぴぷぺぽ", "m": "まみむめも", "r": "らりるれろ",
}
ROMAJI = {consonant + vowel: kana for consonant, row in _ROWS.items() for vowel, kana in zip(VOWELS, row)}
ROMAJI |= {"ya": "や", "yu": "ゆ", "yo": "よ", "wa": "わ", "wo": "を"}
ROMAJI |= {"shi": "し", "chi": "ち", "tsu": "つ", "fu": "ふ", "ji": "じ"}
# Contracted sounds: kya, sha, cho, ...
for consonant in "kgnhbpmr":
    for vowel, small in zip("auo", "ゃゅょ"):
        ROMAJI[consonant + "y" + vowel] = ROMAJI[consonant + "i"] + small
for start, base in {"sh": "し", "ch": "ち", "j": "じ", "sy": "し", "ty": "ち", "zy": "じ"}.items():
    for vowel, small in zip("auo", "ゃゅょ"):
        ROMAJI[start + vowel] = base + small


def romaji_to_hiragana(text: str) -> str:
    """Convert Hepburn-style romaji to hiragana, e.g. "konnichiwa" -> "こんにちわ".

    Characters that aren't romaji are kept as they are.
    """
    text = text.lower()
    out = []
    i = 0
    while i < len(text):
        char, rest = text[i], text[i + 1 :]
        if char == "n" and (not rest or rest[0] not in VOWELS + "y"):
            out.append("ん")  # n before a consonant or at the end; "n'" and "nn" too
            i += 2 if rest[:1] == "'" else 1
            continue
        if char not in VOWELS + "n" and rest[:1] == char:
            out.append("っ")  # doubled consonant: kitte -> きって
            i += 1
            continue
        for length in (3, 2, 1):
            if (piece := text[i : i + length]) in ROMAJI:
                out.append(ROMAJI[piece])
                i += length
                break
        else:
            out.append(char)
            i += 1
    return "".join(out)


# Kanji followed by a hiragana reading in brackets, e.g. 食(た)べる or 日本語（にほんご）
FURIGANA = re.compile(r"([一-鿿々]+)[(（]([ぁ-ゖー]+)[)）]")


def with_furigana(markdown: str) -> str:
    """Show readings written as 漢字(かんじ) above the kanji instead of in brackets."""
    return FURIGANA.sub(r"<ruby>\1<rp>(</rp><rt>\2</rt><rp>)</rp></ruby>", markdown)
