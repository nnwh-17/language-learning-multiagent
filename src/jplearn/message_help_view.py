"""Translate and Words buttons on each tutor message, and the side panel they open.

A script adds two buttons next to each tutor message's copy button. Clicking one sends the
message's text (without furigana or the collapsed agent steps) to the server through a
hidden textbox and button, and the server opens the side panel on its Message help tab:

- Translate: an English translation of each Japanese sentence in the message.
- Words: a box for words copied from the message, each explained simply. Text selected in
  the message when Words is clicked is filled in for you.
"""

import json

import gradio as gr
from pydantic import BaseModel

from jplearn.agents.message_help import MessageTranslation, WordHelp, message_translator, word_helper, words_prompt
from jplearn.reader_view import JAPANESE, items_in
from jplearn.tokenizer import tokenize_placed

MAX_MESSAGE = 4000
MAX_WORDS = 200
TAB_ID = "message-help"
NO_MESSAGE = "_Press Translate or Words under a tutor message to open it here._"
TRANSLATE_HINT = "_Press Translate for an English version._"
TRANSLATING = "⏳ Translating…"


class Request(BaseModel):
    mode: str = "translate"  # "translate" or "words"
    text: str = ""
    selection: str = ""


def parse_request(payload: str) -> Request:
    """The hidden textbox's JSON, written by the buttons' script."""
    try:
        return Request.model_validate(json.loads(payload))
    except ValueError:
        return Request()


def message_preview(text: str) -> str:
    """The start of the message, quoted, so the learner knows which one the panel is about."""
    short = " ".join(text.split())
    short = short if len(short) <= 160 else short[:160].rstrip() + "…"
    return f"> {short}" if short else NO_MESSAGE


def dictionary_lines(words: str) -> str:
    """The pasted words' tokens and JMdict meanings, one per line (no model)."""
    items, seen = items_in(tokenize_placed(words), 0, len(words)), set()
    lines = []
    for i in items:
        if (i.kind, i.key) in seen:
            continue
        seen.add((i.kind, i.key))
        reading = f" ({i.reading})" if i.reading and i.reading != i.key else ""
        lines.append(f"- {i.surface} → {i.key}{reading} [{i.kind}]: {i.meaning or '?'}")
    return "\n".join(lines)


def translation_markdown(result: MessageTranslation) -> str:
    if not result.lines:
        return "_No Japanese found in this message._"
    return "\n\n".join(f"**{line.japanese}**  \n{line.english}" for line in result.lines)


def words_markdown(result: WordHelp) -> str:
    if not result.notes:
        return "_Nothing to explain there. Paste a word from the message._"
    parts = []
    for note in result.notes:
        reading = f" ({note.reading})" if note.reading and note.reading != note.word else ""
        parts.append(
            f"#### {note.word}{reading}\n"
            f"**{note.meaning}**. {note.here}\n\n"
            f"例: {note.example}  \n_{note.example_english}_"
        )
    return "\n\n".join(parts)


def _error(e: Exception) -> str:
    return f"⚠️ Something went wrong, please try again. `{type(e).__name__}: {e}`"


def open_panel(payload: str, current: str):
    """Values for [message, preview, translation, words box, notes, sidebar, side tabs, menu].

    Reopening the message already shown keeps its translation and notes, so the learner can
    switch between Translate and Words without losing either."""
    request = parse_request(payload)
    text = request.text.strip()[:MAX_MESSAGE]
    same = text == current
    selection = request.selection.strip()[:MAX_WORDS] if request.mode == "words" else ""
    if same:
        translation = gr.skip()
        words, notes = selection or gr.skip(), gr.skip()
    else:
        translation, words, notes = TRANSLATE_HINT, selection, ""
    return (
        text,
        message_preview(text),
        translation,
        words,
        notes,
        gr.Sidebar(open=True),
        gr.Tabs(selected=TAB_ID),
        gr.Sidebar(open=False),
    )


def after_open(payload: str, translation: str):
    """Whether the Translate button was pressed and the message has no translation yet."""
    unfinished = translation in (TRANSLATE_HINT, NO_MESSAGE, "") or translation.startswith("⚠️")
    return parse_request(payload).mode == "translate" and unfinished


async def translate(text: str, payload: str | None = None, shown: str = ""):
    """Values for [translation]. With `payload` (after a message's button), only runs for the
    Translate button, and not again for a message already translated."""
    if payload is not None and not after_open(payload, shown):
        yield gr.skip()
        return
    if not text.strip():
        yield NO_MESSAGE
        return
    if not JAPANESE.search(text):
        yield "_This message has no Japanese to translate._"
        return
    yield TRANSLATING
    try:
        result = await message_translator.run(f"Message:\n{text}")
    except Exception as e:
        yield _error(e)
        return
    yield translation_markdown(result.output)


async def explain_words(text: str, words: str):
    """Values for [notes]: the dictionary at once, then the helper's simple notes."""
    words = words.strip()[:MAX_WORDS]
    if not text.strip():
        yield NO_MESSAGE
        return
    if not words:
        yield "Paste a word or phrase from the message first."
        return
    found = dictionary_lines(words)
    dictionary = f"**Dictionary**\n\n{found}" if found else ""
    yield f"⏳ Explaining…\n\n{dictionary}".strip()
    try:
        result = await word_helper.run(words_prompt(text, words, found))
    except Exception as e:
        yield f"{_error(e)}\n\n{dictionary}".strip()
        return
    yield words_markdown(result.output)


# Icons from Lucide (ISC licence): "languages" and "book-open"
TRANSLATE_ICON = (
    '<path d="m5 8 6 6"/><path d="m4 14 6-6 2-3"/><path d="M2 5h12"/><path d="M7 2h1"/>'
    '<path d="m22 22-5-10-5 10"/><path d="M14 18h6"/>'
)
WORDS_ICON = (
    '<path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5'
    'a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>'
)

# Watches the chat and gives every tutor message's button row the two extra buttons.
# Gradio groups a run of tutor messages (agent steps + reply) into one row with one set of
# buttons, so a button sends the text of its whole row, minus the collapsed steps.
BUTTONS_JS = """
const ICONS = __ICONS__;
const svg = (paths) => '<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" '
  + 'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + paths + '</svg>';
let selection = '';  // text selected in a message when a button was pressed

function rowOf(buttons) {
  const row = buttons.previousElementSibling;
  return row && row.classList.contains('bot-row') ? row : null;
}
function messageText(row) {
  const parts = [...row.querySelectorAll('.message-content')].filter((el) => !el.closest('.thought-group'));
  return parts.map((el) => {
    const copy = el.cloneNode(true);
    copy.querySelectorAll('rt, rp, button, svg, .tts').forEach((n) => n.remove());
    copy.querySelectorAll('br').forEach((n) => n.replaceWith('\\n'));
    copy.querySelectorAll('p, li, tr, h1, h2, h3, h4, h5, h6, pre, blockquote').forEach((n) => n.append('\\n'));
    copy.querySelectorAll('td, th').forEach((n) => n.append(' | '));
    return copy.textContent.replace(/[ \\t]+\\n/g, '\\n').replace(/\\n{3,}/g, '\\n\\n').trim();
  }).filter(Boolean).join('\\n\\n');
}
function selectionIn(row) {
  const sel = window.getSelection();
  if (!sel.rangeCount || sel.isCollapsed) return '';
  const range = sel.getRangeAt(0);
  if (!row.contains(range.commonAncestorContainer)) return '';
  const copy = range.cloneContents();  // without the furigana above the kanji
  copy.querySelectorAll('rt, rp').forEach((n) => n.remove());
  return copy.textContent.trim();
}
function send(mode, row) {
  const box = document.querySelector('#msg-help-request textarea, #msg-help-request input');
  const go = document.querySelector('#msg-help-go');
  if (!box || !go) return;
  const payload = JSON.stringify({ mode, text: messageText(row), selection, nonce: Date.now() });
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(box), 'value').set;
  setter.call(box, payload);
  box.dispatchEvent(new Event('input', { bubbles: true }));
  selection = '';
  setTimeout(() => {
    go.click();
    if (mode === 'words') setTimeout(() => document.querySelector('#msg-help-words textarea')?.focus(), 400);
  }, 50);
}
function button(mode, title, row) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'icon-button padded msg-help-btn';
  b.title = title;
  b.setAttribute('aria-label', title);
  b.dataset.mode = mode;
  b.innerHTML = svg(ICONS[mode]);
  b.addEventListener('pointerdown', () => { const r = rowOf(b.closest('.message-buttons')); selection = r ? selectionIn(r) : ''; });
  b.addEventListener('click', () => { const r = rowOf(b.closest('.message-buttons')); if (r) send(mode, r); });
  return b;
}
function addButtons() {
  for (const buttons of document.querySelectorAll('#chat .message-buttons-left')) {
    const wrap = buttons.querySelector('.icon-button-wrapper');
    if (!wrap || wrap.querySelector('.msg-help-btn') || !rowOf(buttons)) continue;
    wrap.append(button('translate', 'Translate to English'), button('words', 'Explain words from this message'));
  }
}
new MutationObserver(addButtons).observe(document.body, { childList: true, subtree: true });
addButtons();
"""


def buttons_script() -> tuple[gr.Textbox, gr.Button]:
    """Put in the Chat tab: an invisible element whose script adds the buttons to the chat's
    messages, and the hidden textbox and button the script sends a message through. They sit
    here, not in the side panel, because a closed panel's contents aren't on the page."""
    icons = json.dumps({"translate": TRANSLATE_ICON, "words": WORDS_ICON})
    gr.HTML("", js_on_load=BUTTONS_JS.replace("__ICONS__", icons), elem_id="msg-help-script", container=False)
    request = gr.Textbox(elem_id="msg-help-request", visible="hidden")
    go = gr.Button("open", elem_id="msg-help-go", visible="hidden")
    return request, go


def build():
    """The Message help tab's contents. Returns (message, preview, translation, translate_btn,
    words, notes) for wiring in web.py."""
    message = gr.State("")  # plain text of the message the panel is about
    preview = gr.Markdown(NO_MESSAGE, elem_id="msg-help-preview")
    gr.Markdown("#### English")
    translation = gr.Markdown(TRANSLATE_HINT, elem_id="msg-help-translation")
    translate_btn = gr.Button("Translate", variant="secondary", size="sm", elem_classes="msg-help-action")
    gr.Markdown("#### Words")
    words = gr.Textbox(
        elem_id="msg-help-words",
        show_label=False,
        placeholder="Paste words you don't know from the message, e.g. 天気, 行きました",
        lines=1,
        max_lines=3,
        submit_btn="Explain",
    )
    notes = gr.Markdown(elem_id="msg-help-notes")
    return message, preview, translation, translate_btn, words, notes
