"""The web UI's Read & translate tab: highlight what you don't know, translate, then study it.

1. The learner pastes a text. It is shown with readings on hover (tokenizer, no model).
2. They press a key of their choice to switch to the highlight cursor and select the words
   and grammar they don't know, like using a highlighter pen. Selections snap to whole
   tokens, and each highlight is broken down straight away from the tokenizer, JMdict and
   grammar_notes.py, again without a model.
3. They write their own translation; the translation checker (the tab's one model call)
   reviews it, and the part of the text behind each mistake is highlighted too. In offline
   mode there is no model call: the translation is compared with each word's dictionary
   meanings instead (``self_check_markdown``), as a rough guide the learner checks themselves.
4. The highlights become a quiz (readings, meanings, particles; built here, no model) or
   Anki cards, added only when the learner clicks Add.
"""

import html
import random
import re
import uuid
from typing import Literal

import gradio as gr
from pydantic import BaseModel

from jplearn import quiz_view
from jplearn.agents.analyzer import LOOKUP_POS
from jplearn.agents.flashcards import Card, add_cards
from jplearn.agents.quiz import BLANK, Question, Quiz
from jplearn.agents.translation import TranslationReview, review_prompt, translation_checker
from jplearn.config import DEFAULT_DECK
from jplearn.dictionary import lookup
from jplearn.grammar_notes import GRAMMAR_NOTES, TE_PATTERNS
from jplearn.kana import with_furigana
from jplearn.quiz_view import QuizSession
from jplearn.tokenizer import PlacedToken, tokenize_placed

MAX_CHARS = 1000
JAPANESE = re.compile(r"[぀-ヿ一-鿿]")
KANJI = re.compile(r"[一-鿿々]")
SENTENCE = re.compile(r"[^。！？!?\n]+[。！？!?]*")
CONTENT_POS = LOOKUP_POS | {"prefix", "suffix"}
MAX_QUESTIONS = 10


class Highlight(BaseModel):
    start: int  # character offsets in the text, on token boundaries
    end: int
    source: Literal["you", "mistake"] = "you"  # "mistake": added from the translation review


class Item(BaseModel):
    """One thing to study, found in a highlight: a word, or a grammar point."""

    kind: Literal["vocab", "grammar"]
    key: str  # dictionary form, or grammar pattern (e.g. 〜てしまう)
    surface: str  # as it appears in the text
    reading: str  # reading of `key` (grammar: "")
    meaning: str
    note: str = ""  # the form used in the text, e.g. "食べ, continuative (masu/te stem)"
    particle: bool = False  # a single particle, which can be quizzed by blanking it out
    start: int
    end: int


class Reading(BaseModel):
    text: str
    highlights: list[Highlight] = []  # sorted, not overlapping
    review: TranslationReview | None = None

    def tokens(self) -> list[PlacedToken]:
        return tokenize_placed(self.text)


# --- highlights ---


def add_highlight(reading: Reading, start: int, end: int, source: str = "you") -> Reading:
    """Highlight the tokens touched by text[start:end], merging highlights that overlap."""
    touched = [t for t in reading.tokens() if t.start < end and t.end > start]
    if not touched:
        return reading  # only punctuation or spaces selected
    new = Highlight(start=touched[0].start, end=touched[-1].end, source=source)
    kept = []
    for old in reading.highlights:
        if old.start < new.end and old.end > new.start:
            source = "you" if "you" in (old.source, new.source) else "mistake"
            new = Highlight(start=min(old.start, new.start), end=max(old.end, new.end), source=source)
        else:
            kept.append(old)
    highlights = sorted([*kept, new], key=lambda h: h.start)
    return reading.model_copy(update={"highlights": highlights})


def remove_highlight(reading: Reading, at: int) -> Reading:
    highlights = [h for h in reading.highlights if not h.start <= at < h.end]
    return reading.model_copy(update={"highlights": highlights})


# --- breaking highlights down (no model) ---


def _meaning(token: PlacedToken) -> str:
    entries = lookup(token.lemma, token.lemma_reading, max_entries=1)
    return "; ".join(entries[0].senses[0].meanings[:3]) if entries and entries[0].senses else ""


def items_in(tokens: list[PlacedToken], start: int, end: int) -> list[Item]:
    """The words and grammar in text[start:end]. て + いる etc. become one pattern (〜ている)."""
    items = []
    for i, token in enumerate(tokens):
        if not (start <= token.start and token.end <= end):
            continue
        before = tokens[i - 1] if i else None
        after = tokens[i + 1] if i + 1 < len(tokens) else None
        after_te = before is not None and before.surface in ("て", "で") and before.pos == "particle"
        place = {"start": token.start, "end": token.end}
        if token.pos == "particle" and token.surface in ("て", "で") and after and after.lemma in TE_PATTERNS and after.end <= end:
            continue  # explained with the verb after it
        if token.pos == "verb" and after_te and token.lemma in TE_PATTERNS:
            pattern, meaning = TE_PATTERNS[token.lemma]
            items.append(Item(kind="grammar", key=pattern, surface=before.surface + token.surface, reading="", meaning=meaning,
                              start=max(before.start, start), end=token.end))
        elif token.pos in ("particle", "auxiliary verb"):
            meaning = GRAMMAR_NOTES.get(token.lemma, f"{token.pos} ({token.pos_detail})")
            items.append(Item(kind="grammar", key=token.lemma, surface=token.surface, reading="", meaning=meaning,
                              particle=token.pos == "particle", **place))
        elif token.pos in CONTENT_POS:
            note = f"{token.surface}, {token.conjugation}" if token.conjugation and token.surface != token.lemma else ""
            items.append(Item(kind="vocab", key=token.lemma, surface=token.surface, reading=token.lemma_reading,
                              meaning=_meaning(token), note=note, **place))
    return items


def study_items(reading: Reading) -> list[Item]:
    """Everything highlighted, each word or grammar point once, in text order."""
    tokens, items = reading.tokens(), {}
    for highlight in reading.highlights:
        for item in items_in(tokens, highlight.start, highlight.end):
            items.setdefault((item.kind, item.key), item)
    return list(items.values())


def word_list(reading: Reading) -> str:
    """The whole text's words and grammar, one per line, for the translation checker."""
    items = items_in(reading.tokens(), 0, len(reading.text))
    return "\n".join(
        f"- {i.surface} → {i.key}{f' ({i.reading})' if i.reading and i.reading != i.key else ''} [{i.kind}]: {i.meaning}"
        for i in items
    )


# --- rendering ---

PANE_TEMPLATE = """
<div class="hl-bar">
  <button class="hl-toggle" type="button">
    <span class="mode-off">🖱️ Normal cursor</span><span class="mode-on">🖍️ Highlighter on</span>
  </button>
  <span class="hl-help">Press <kbd class="hl-key">H</kbd> to switch ·
    <button class="hl-setkey" type="button">Change key</button></span>
</div>
${value}
"""

# Selections are sent to Python as character offsets. Every piece of text is a span with
# its offset in data-s; offsets are counted in code points, as Python does.
PANE_JS = """
const root = document.documentElement;
const KEY = 'jplearn-highlight-key';
const getKey = () => { try { return localStorage.getItem(KEY) || 'h'; } catch (e) { return 'h'; } };
const keyName = (k) => k === ' ' ? 'Space' : k.length === 1 ? k.toUpperCase() : k;
const showKey = () => document.querySelectorAll('.hl-key').forEach((el) => el.textContent = keyName(getKey()));
const setMode = (on) => { root.dataset.hl = on ? 'on' : 'off'; };

if (!window.jplearnHighlightKeys) {  // once per page, however often the tab re-renders
  window.jplearnHighlightKeys = true;
  document.addEventListener('keydown', (e) => {
    if (root.dataset.hlCapture === 'on') {  // choosing a new key
      if (['Shift', 'Control', 'Alt', 'Meta'].includes(e.key)) return;
      e.preventDefault();
      if (e.key !== 'Escape') {
        try { localStorage.setItem(KEY, e.key); } catch (err) {}
      }
      delete root.dataset.hlCapture;
      document.querySelectorAll('.hl-setkey').forEach((b) => b.textContent = 'Change key');
      showKey();
      return;
    }
    const typing = e.target.closest && e.target.closest('input, textarea, select, [contenteditable="true"]');
    if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key.toLowerCase() === getKey().toLowerCase()) {
      e.preventDefault();
      setMode(root.dataset.hl !== 'on');
    } else if (e.key === 'Escape' && root.dataset.hl === 'on') {
      setMode(false);
    }
  });
}

const length = (s) => Array.from(s).length;
function offset(node, at) {
  if (node.nodeType === Node.TEXT_NODE) {
    const piece = node.parentElement.closest('[data-s]');
    return piece ? +piece.dataset.s + length(node.data.slice(0, at)) : null;
  }
  const piece = node.closest && node.closest('[data-s]');
  if (piece) return +piece.dataset.s + (at ? length(piece.textContent) : 0);
  const child = node.childNodes[at];
  if (child && child.dataset && child.dataset.s) return +child.dataset.s;
  const text = element.querySelector('.reader-text');
  return text ? +text.dataset.len : null;
}

let justSelected = false;
element.addEventListener('mouseup', () => {
  const text = element.querySelector('.reader-text');
  const selection = window.getSelection();
  if (root.dataset.hl !== 'on' || !text || !selection.rangeCount || selection.isCollapsed) return;
  const range = selection.getRangeAt(0);
  if (!text.contains(range.startContainer) || !text.contains(range.endContainer)) return;
  const start = offset(range.startContainer, range.startOffset);
  const end = offset(range.endContainer, range.endOffset);
  selection.removeAllRanges();
  if (start !== null && end !== null && end > start) {
    justSelected = true;
    trigger('select', {action: 'add', start: start, end: end});
  }
});
element.addEventListener('click', (e) => {
  if (e.target.closest('.hl-toggle')) { setMode(root.dataset.hl !== 'on'); return; }
  if (e.target.closest('.hl-setkey')) {
    root.dataset.hlCapture = 'on';
    e.target.closest('.hl-setkey').textContent = 'Press a key…';
    return;
  }
  if (justSelected) { justSelected = false; return; }
  const piece = e.target.closest('.hl[data-s]');
  if (root.dataset.hl === 'on' && piece && window.getSelection().isCollapsed) {
    trigger('select', {action: 'remove', start: +piece.dataset.s, end: +piece.dataset.s});
  }
});
showKey();
watch('value', showKey);
"""


def render_text(reading: Reading | None) -> str:
    """The text as spans that the pane's script can map selections back from."""
    if reading is None:
        return "<div class='reader-empty'>Paste a text above and click <b>Start reading</b>.</div>"
    text, tokens = reading.text, reading.tokens()
    cuts = {0, len(text)} | {t.start for t in tokens} | {t.end for t in tokens}
    cuts |= {h.start for h in reading.highlights} | {h.end for h in reading.highlights}
    token_at = {t.start: t for t in tokens}
    e, pieces, points = html.escape, [], sorted(cuts)
    for start, end in zip(points, points[1:]):
        covering = [h for h in reading.highlights if h.start <= start and end <= h.end]
        css = f' class="hl {covering[0].source}"' if covering else ""
        token = token_at.get(start)
        title = f' title="{e(token.reading)}"' if token and token.reading != token.surface else ""
        pieces.append(f'<span data-s="{start}"{css}{title}>{e(text[start:end])}</span>')
    return f"<div class='reader-text' data-len='{len(text)}'>{''.join(pieces)}</div>"


def breakdown_markdown(reading: Reading) -> str:
    if not reading.highlights:
        return "_Nothing highlighted yet. Switch to the highlighter and select what you don't know._"
    tokens, seen, blocks = reading.tokens(), set(), []
    for highlight in reading.highlights:
        lines = [f"**{reading.text[highlight.start:highlight.end]}**"
                 + (" · _from your translation_" if highlight.source == "mistake" else "")]
        for item in items_in(tokens, highlight.start, highlight.end):
            if (item.kind, item.key) in seen:
                lines.append(f"- {item.key}: _see above_")
                continue
            seen.add((item.kind, item.key))
            if item.kind == "vocab":
                reading_text = f"（{item.reading}）" if item.reading != item.key else ""
                note = f" · here: {item.note}" if item.note else ""
                lines.append(f"- **{item.key}**{reading_text} {item.meaning or '_not in the dictionary_'}{note}")
            else:
                lines.append(f"- **{item.key}** _grammar_ · {item.meaning}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def review_markdown(review: TranslationReview) -> str:
    lines = [f"**{review.verdict.capitalize()}.** {review.summary}", ""]
    if review.mistakes:
        lines.append("#### What to fix")
        for i, mistake in enumerate(review.mistakes, 1):
            wrote = f"you wrote “{mistake.you_wrote}”" if mistake.you_wrote else "left out"
            lines.append(f"{i}. **{mistake.japanese}**: {wrote} → “{mistake.better}”  ")
            lines.append(f"   {mistake.problem}")
        lines += ["", "_The parts you got wrong are now highlighted too, so they're in your quiz and cards._", ""]
    if review.got_right:
        lines += ["#### You got right", *(f"- {item}" for item in review.got_right), ""]
    lines += ["#### A natural translation", f"> {review.reference}"]
    return with_furigana("\n".join(lines))


# --- offline mode: checking a translation against the dictionary (no model) ---

# Words that say nothing about whether a meaning was translated
STOPWORDS = {
    "a", "an", "the", "to", "of", "in", "on", "at", "by", "for", "with", "from", "as", "or", "and",
    "be", "is", "are", "am", "was", "were", "been", "it", "one", "someone", "something", "oneself",
    "one's", "etc", "esp", "very", "also", "not", "do", "does", "did",
}
# Common irregular forms, mapped to the base form dictionary glosses use
IRREGULAR = {
    "ate": "eat", "eaten": "eat", "went": "go", "gone": "go", "goes": "go", "saw": "see", "seen": "see",
    "had": "have", "has": "have", "made": "make", "came": "come", "took": "take", "taken": "take",
    "gave": "give", "given": "give", "said": "say", "got": "get", "bought": "buy", "drank": "drink",
    "wrote": "write", "written": "write", "ran": "run", "slept": "sleep", "met": "meet",
    "thought": "think", "felt": "feel", "left": "leave", "knew": "know", "known": "know",
    "spoke": "speak", "spoken": "speak", "taught": "teach", "found": "find", "heard": "hear",
    "sat": "sit", "stood": "stand", "became": "become", "began": "begin", "brought": "bring",
    "children": "child", "people": "person", "men": "man", "women": "woman", "mice": "mouse",
}


def _stem(word: str) -> str:
    """A rough base form, so 'studied', 'studies' and 'study' match each other."""
    if word in IRREGULAR:
        return IRREGULAR[word]
    if word.endswith(("ied", "ies")) and len(word) > 4:
        return word[:-3] + "y"
    for suffix in ("ing", "ed", "es", "s", "ly"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _stems(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z']+", text.lower()) if w not in STOPWORDS and len(w) > 1}


def _all_meanings(item: Item) -> list[str]:
    entries = lookup(item.key, item.reading or None, max_entries=1)
    return [m for sense in entries[0].senses for m in sense.meanings] if entries else []


def self_check(reading: Reading, translation: str) -> list[tuple[Item, bool | None]]:
    """Each word in the text, with whether one of its dictionary meanings appears in the
    translation (None: not in the dictionary, so it can't be checked)."""
    said = _stems(translation)
    rows, seen = [], set()
    for item in items_in(reading.tokens(), 0, len(reading.text)):
        # する is almost always part of a noun + する verb (勉強する), so it's checked with its noun
        if item.kind != "vocab" or item.key in seen or item.key == "する":
            continue
        seen.add(item.key)
        meanings = _all_meanings(item)
        rows.append((item, any(_stems(m) & said for m in meanings) if meanings else None))
    return rows


def self_check_markdown(reading: Reading, translation: str) -> str:
    rows = self_check(reading, translation)
    checked = [found for _, found in rows if found is not None]
    lines = [
        f"**Self-check (offline, no AI).** Your translation uses the dictionary meaning of "
        f"**{sum(checked)} of {len(checked)}** words. This is a rough guide: a synonym or a natural "
        "rewording counts as missed here, so judge each ❔ yourself.",
        "",
    ]
    if rows:
        lines += ["| Word | Reading | Dictionary meaning | In your translation? |", "|---|---|---|---|"]
        status = {True: "✅ found", False: "❔ possibly missed", None: "— not in the dictionary"}
        for item, found in rows:
            word = item.key if item.surface == item.key else f"{item.surface} → {item.key}"
            reading_text = item.reading if item.reading != item.key else ""
            lines.append(f"| {word} | {reading_text} | {item.meaning or '–'} | {status[found]} |")
        lines.append("")
    grammar = {(i.key, i.meaning) for i in items_in(reading.tokens(), 0, len(reading.text)) if i.kind == "grammar"}
    if grammar:
        lines += ["#### Grammar to check you covered", *(f"- **{key}** · {meaning}" for key, meaning in sorted(grammar)), ""]
    lines.append("_Highlight anything you missed, so it's in your quiz and cards._")
    return "\n".join(lines)


# --- studying: quizzes and cards (no model) ---


def _sentence_at(text: str, position: int) -> tuple[int, str]:
    """(start, sentence) of the sentence containing text[position]."""
    for match in SENTENCE.finditer(text):
        if match.start() <= position < match.end():
            return match.start(), match.group()
    return 0, text


def make_quiz(reading: Reading) -> Quiz | None:
    """Questions on the highlighted items: readings, meanings, and particles blanked out."""
    items = study_items(reading)
    rng = random.Random(reading.text)  # the same text gets the same options
    # Wrong options: other words' meanings from the text, or other grammar notes
    word_meanings = list(dict.fromkeys(
        i.meaning for i in items_in(reading.tokens(), 0, len(reading.text)) if i.kind == "vocab" and i.meaning
    ))
    grammar_meanings = list(dict.fromkeys([*GRAMMAR_NOTES.values(), *(m for _, m in TE_PATTERNS.values())]))

    def choice(prompt: str, answer: str, pool: list[str], explanation: str) -> Question | None:
        wrong = [m for m in pool if m != answer]
        if len(wrong) < 2:
            return None
        options = [answer, *rng.sample(wrong, min(3, len(wrong)))]
        rng.shuffle(options)
        return Question(kind="choice", prompt=prompt, options=options, answer=answer, explanation=explanation)

    questions = []
    for item in items:
        if item.kind == "vocab":
            if KANJI.search(item.key) and item.reading:
                questions.append(Question(
                    kind="reading", prompt="How do you read this word?", word=item.key, answer=item.reading,
                    explanation=f"{item.key} is read {item.reading}" + (f": {item.meaning}." if item.meaning else "."),
                ))
            if item.meaning:
                questions.append(choice(f"What does **{item.key}** mean?", item.meaning, word_meanings,
                                        f"{item.key}（{item.reading}）: {item.meaning}."))
        elif item.particle:
            offset, sentence = _sentence_at(reading.text, item.start)
            gap = sentence[: item.start - offset] + BLANK + sentence[item.end - offset :]
            questions.append(Question(
                kind="fill_in", prompt=f"{gap.strip()}\n\nWhich particle goes in the gap?",
                answer=item.surface, explanation=f"{item.surface}: {item.meaning}.",
            ))
        else:
            questions.append(choice(f"What does **{item.key}** do in “{item.surface}”?", item.meaning,
                                    grammar_meanings, f"{item.key}: {item.meaning}."))
    questions = [q for q in questions if q is not None][:MAX_QUESTIONS]
    return Quiz(title="Your highlights", questions=questions) if questions else None


def draft_cards(reading: Reading) -> list[Card]:
    """A card for each highlighted item, with its sentence from the text as the example."""
    text = reading.text.strip()
    cards = []
    for item in study_items(reading):
        sentence = _sentence_at(reading.text, item.start)[1].strip()
        # The reviewed translation is of the whole text, so it only fits a one-sentence text
        translation = reading.review.reference if reading.review and sentence == text else ""
        cards.append(Card(
            kind=item.kind, front=item.key, reading=item.reading, meaning=item.meaning or "(not in the dictionary)",
            example=sentence, example_translation=translation, notes=item.note or None,
        ))
    return cards


def cards_markdown(cards: list[Card]) -> str:
    if not cards:
        return "Highlight something in the text first."

    def cell(text: str | None) -> str:
        return (text or "").replace("|", "\\|").replace("\n", " ")

    rows = "\n".join(
        f"| {c.kind} | {cell(c.front)} | {cell(c.reading)} | {cell(c.meaning)} | {cell(c.example)} |" for c in cards
    )
    return (
        f"**{len(cards)} cards.** Nothing is added to Anki until you click **Add to Anki**.\n\n"
        "| Type | Front | Reading | Meaning | Example |\n|---|---|---|---|---|\n" + rows
    )


# --- event handlers ---


def start_reading(text: str):
    """Values for [reading, status, workspace, pane, breakdown, translation, feedback, cards,
    cards_box, quiz_state, *quiz_ui, quiz_results]."""
    text = text.strip()
    if not JAPANESE.search(text) or len(text) > MAX_CHARS:
        problem = "Paste some Japanese text first." if len(text) <= MAX_CHARS else (
            f"That's {len(text)} characters; paste up to {MAX_CHARS} at a time."
        )
        return gr.skip(), problem, *(gr.skip(),) * (START_SIZE - 2)
    reading = Reading(text=text)
    return (
        reading, "", gr.Column(visible=True), render_text(reading), breakdown_markdown(reading),
        "", "", [], gr.Column(visible=False), None, *quiz_view.render(None), "",
    )


START_SIZE = 11 + quiz_view.UI_SIZE  # values in start_reading's outputs


def on_select(reading: Reading | None, evt: gr.EventData):
    """The learner highlighted text, or clicked a highlight to remove it. Values for [reading, pane, breakdown]."""
    if reading is None:
        return gr.skip(), gr.skip(), gr.skip()
    if evt.action == "add":
        reading = add_highlight(reading, int(evt.start), int(evt.end))
    else:
        reading = remove_highlight(reading, int(evt.start))
    return reading, render_text(reading), breakdown_markdown(reading)


def clear_highlights(reading: Reading | None):
    if reading is None:
        return gr.skip(), gr.skip(), gr.skip()
    reading = reading.model_copy(update={"highlights": []})
    return reading, render_text(reading), breakdown_markdown(reading)


def _error(e: Exception) -> str:
    return f"⚠️ Something went wrong, please try again. `{type(e).__name__}: {e}`"


async def check_translation(reading: Reading | None, translation: str, offline: bool = False):
    """Values for [reading, feedback, pane, breakdown]. Offline: a dictionary self-check, no model."""
    skip = (gr.skip(),) * 2
    if reading is None:
        yield gr.skip(), "Start reading a text first.", *skip
        return
    if not translation.strip():
        yield gr.skip(), "Write your translation first, even a rough one.", *skip
        return
    if offline:
        yield gr.skip(), self_check_markdown(reading, translation), *skip
        return
    yield gr.skip(), "⏳ Checking your translation…", *skip
    highlighted = [reading.text[h.start : h.end] for h in reading.highlights]
    prompt = review_prompt(reading.text, word_list(reading), highlighted, translation.strip())
    try:
        result = await translation_checker.run(prompt)
    except Exception as e:
        yield gr.skip(), _error(e), *skip
        return
    reading = reading.model_copy(update={"review": result.output})
    for mistake in result.output.mistakes:
        if mistake.japanese and (at := reading.text.find(mistake.japanese)) >= 0:
            reading = add_highlight(reading, at, at + len(mistake.japanese), source="mistake")
    yield reading, review_markdown(result.output), render_text(reading), breakdown_markdown(reading)


def start_quiz(reading: Reading | None):
    """Values for [study_status, quiz_state, *quiz_ui, quiz_results]."""
    quiz = make_quiz(reading) if reading else None
    if quiz is None:
        return "Highlight something in the text first.", *(gr.skip(),) * (2 + quiz_view.UI_SIZE)
    session = QuizSession(id=uuid.uuid4().hex, quiz=quiz)
    return "", session, *quiz_view.render(session), ""


def advance_quiz(session: QuizSession | None):
    """Next question, or the results after the last one. Values for [quiz_state, *quiz_ui, quiz_results]."""
    if session is not None and session.checked and not session.is_last:
        session = quiz_view.next_question(session)
        return session, *quiz_view.render(session), gr.skip()
    return end_quiz(session)


def end_quiz(session: QuizSession | None):
    if session is None:
        return (gr.skip(),) * (2 + quiz_view.UI_SIZE)
    return None, *quiz_view.render(None), quiz_view.results_markdown(session)


def make_cards(reading: Reading | None):
    """Values for [cards, cards_box, cards_preview, anki_status]."""
    if reading is None:
        return [], gr.Column(visible=False), "", ""
    cards = draft_cards(reading)
    return cards, gr.Column(visible=True), cards_markdown(cards), ""


async def add_to_anki(cards: list[Card], deck: str):
    """Clicking Add is the learner's approval for exactly the cards shown."""
    if not cards:
        yield "Make flashcards first."
        return
    deck = deck.strip() or DEFAULT_DECK
    yield "⏳ Adding to Anki…"
    try:
        await add_cards(deck, cards)
    except Exception as e:
        yield f"⚠️ Couldn't add the cards. Is Anki open with AnkiConnect installed? `{type(e).__name__}: {e}`"
        return
    yield f"✅ Sent {len(cards)} card{'s' * (len(cards) != 1)} to **{deck}**. Anki skips any you already have."


# --- layout ---

INTRO = """### Read & translate
Paste a Japanese text and highlight what you don't know. Translate it in your own words and
get your mistakes explained, then study the breakdown of everything you highlighted."""

CHECK_LABELS = {False: "Check my translation", True: "Compare with the dictionary"}


def build() -> None:
    """Create the tab's components and wire them up, inside the current gr.Blocks."""
    reading = gr.State(None)  # Reading, or None before a text is started
    cards = gr.State([])  # the Cards shown in the preview
    quiz_state = gr.State(None)  # QuizSession for this tab's quiz panel

    gr.Markdown(INTRO)
    offline = gr.Checkbox(
        label="🔌 Offline mode: no AI",
        info="Check your translation against the dictionary instead of asking the AI. "
        "Highlighting, the breakdown, the quiz and the cards never use the AI.",
        value=False,
        elem_id="reader-offline",
    )
    text = gr.Textbox(
        label="Japanese text", lines=4, max_lines=12,
        placeholder="e.g. 昨日、友達と一緒に新しいレストランに行きました。",
    )
    start_btn = gr.Button("Start reading", variant="primary")
    status = gr.Markdown()

    with gr.Column(visible=False) as workspace:
        # Steps 1 and 2 side by side, half the width each (they stack on narrow screens)
        # equal_height + CSS stretch the translation box to the height of the text beside it
        with gr.Row(equal_height=True, elem_id="reader-steps"):
            with gr.Column(scale=1):
                gr.Markdown("#### 1. Highlight what you don't know")
                gr.Markdown(
                    "Switch to the highlighter with your key (or the button), then select words or "
                    "phrases with the mouse. Click a highlight to remove it. Hover a word for its reading.",
                    elem_classes="hint-left",
                )
                pane = gr.HTML(render_text(None), html_template=PANE_TEMPLATE, js_on_load=PANE_JS, elem_id="reader-pane")
                clear_btn = gr.Button("Clear highlights", variant="secondary", size="sm", elem_classes="reader-clear")

            with gr.Column(scale=1):
                gr.Markdown("#### 2. Translate it yourself")
                translation = gr.Textbox(
                    label="Your translation", lines=4, elem_id="reader-translation",
                    placeholder="Write it in English, in your own words",
                )
                check_btn = gr.Button(CHECK_LABELS[False], variant="primary")

        # The review or self-check, full width under both steps (its tables need the room)
        feedback = gr.Markdown(elem_id="reader-feedback")

        gr.Markdown("#### 3. Study your highlights")
        breakdown = gr.Markdown(elem_classes="reader-breakdown")
        with gr.Row():
            quiz_btn = gr.Button("Quiz me", variant="secondary")
            cards_btn = gr.Button("Make flashcards", variant="secondary")
        study_status = gr.Markdown()
        quiz_ui, quiz_end = quiz_view.panel()
        _, _, _, quiz_choices, quiz_typed, _, quiz_check, quiz_next = quiz_ui
        quiz_results = gr.Markdown()
        with gr.Column(visible=False) as cards_box:
            cards_preview = gr.Markdown()
            with gr.Row(equal_height=True):
                deck = gr.Textbox(label="Deck", value=DEFAULT_DECK, scale=3)
                add_btn = gr.Button("Add to Anki", variant="primary", scale=1)
            anki_status = gr.Markdown()

    start_out = [
        reading, status, workspace, pane, breakdown, translation, feedback,
        cards, cards_box, quiz_state, *quiz_ui, quiz_results,
    ]
    start_btn.click(start_reading, text, start_out)
    pane.select(on_select, reading, [reading, pane, breakdown])
    clear_btn.click(clear_highlights, reading, [reading, pane, breakdown])
    check_btn.click(check_translation, [reading, translation, offline], [reading, feedback, pane, breakdown])
    offline.change(lambda on: gr.Button(value=CHECK_LABELS[on]), offline, check_btn, queue=False)

    quiz_out = [quiz_state, *quiz_ui, quiz_results]
    quiz_btn.click(start_quiz, reading, [study_status, *quiz_out])
    check = (quiz_view.check_answer, [quiz_state, quiz_choices, quiz_typed], [quiz_state, *quiz_ui])
    quiz_choices.input(*check)
    quiz_typed.submit(*check)
    quiz_check.click(*check)
    quiz_next.click(advance_quiz, quiz_state, quiz_out)
    quiz_end.click(end_quiz, quiz_state, quiz_out)

    cards_btn.click(make_cards, reading, [cards, cards_box, cards_preview, anki_status])
    add_btn.click(add_to_anki, [cards, deck], anki_status)
