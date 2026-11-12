"""Listen, Translate and Words buttons on each tutor message, and the side panel they open.

A script adds three buttons next to each tutor message's copy button. Listen reads the
message's Japanese aloud in the browser (no server call). Translate and Words send the
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


# Icons from Lucide (ISC licence): "volume-2", "square", "languages" and "book-open"
LISTEN_ICON = (
    '<path d="M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 0 0-1 1v6'
    'a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 0 0 11 19.298z"/>'
    '<path d="M16 9a5 5 0 0 1 0 6"/><path d="M19.364 18.364a9 9 0 0 0 0-12.728"/>'
)
STOP_ICON = '<rect x="6" y="6" width="12" height="12" rx="1"/>'
TRANSLATE_ICON = (
    '<path d="m5 8 6 6"/><path d="m4 14 6-6 2-3"/><path d="M2 5h12"/><path d="M7 2h1"/>'
    '<path d="m22 22-5-10-5 10"/><path d="M14 18h6"/>'
)
WORDS_ICON = (
    '<path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5'
    'a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>'
)

# Watches the chat and gives every tutor message's button row three extra buttons. Gradio
# groups a run of tutor messages (agent steps + reply) into one row with one set of buttons,
# so a button uses the text of its whole row, minus the collapsed steps.
#
# Listen reads only the Japanese in the message (or in the selection, if any) with the
# browser's speech engine, using the voice and speed picked in a Listen bar (speech.py).
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
  b.addEventListener('click', () => {
    const r = rowOf(b.closest('.message-buttons'));
    if (r) mode === 'listen' ? listen(b, r) : send(mode, r);
  });
  return b;
}
// --- Listen: read the Japanese parts aloud ---
const synth = window.speechSynthesis;
const JAPANESE = /[぀-ヿ㐀-鿿豈-﫿々〆ヶ]/;
const RUN = /[　-〿぀-ヿ㐀-鿿豈-﫿！-｠々〆ヶー0-9０-９〜～]+/g;
const LISTEN_TITLE = 'Listen to the Japanese';
let playing = null;  // the Listen button whose message is being read

function japaneseParts(text) {
  return (text.match(RUN) || []).map((s) => s.trim()).filter((s) => JAPANESE.test(s));
}
function stored(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
function japaneseVoice() {
  const voices = synth.getVoices().filter((v) => v.lang.replace('_', '-').toLowerCase().startsWith('ja'));
  const rank = (v) => /natural|online|neural|google/i.test(v.name) ? 0 : v.localService ? 1 : 2;
  const saved = stored('jplearn-tts-voice-ja-JP');  // the voice picked in a Listen bar
  return voices.find((v) => v.voiceURI === saved) || voices.sort((a, b) => rank(a) - rank(b))[0] || null;
}
function showPlaying(b, on) {
  b.innerHTML = svg(on ? ICONS.stop : ICONS.listen);
  b.title = on ? 'Stop' : LISTEN_TITLE;
  b.setAttribute('aria-label', b.title);
  b.classList.toggle('speaking', on);
  playing = on ? b : (playing === b ? null : playing);
}
function listen(b, row) {
  const wasPlaying = playing === b;
  if (playing) showPlaying(playing, false);
  synth.cancel();  // one voice at a time, across the page
  if (wasPlaying) return;
  const parts = japaneseParts(selection || messageText(row));
  selection = '';
  if (!parts.length) {
    b.title = 'No Japanese to read';
    setTimeout(() => { if (playing !== b) b.title = LISTEN_TITLE; }, 2000);
    return;
  }
  const voice = japaneseVoice();
  const rate = +(stored('jplearn-tts-rate') || 0.9);
  parts.forEach((part, i) => {
    const u = new SpeechSynthesisUtterance(part);
    u.lang = voice ? voice.lang : 'ja-JP';
    if (voice) u.voice = voice;
    u.rate = rate;
    if (i === parts.length - 1) u.onend = () => showPlaying(b, false);
    u.onerror = () => showPlaying(b, false);
    synth.speak(u);
  });
  showPlaying(b, true);
}
function listenButton() {
  const b = button('listen', LISTEN_TITLE);
  if (!synth) { b.disabled = true; b.title = 'This browser has no text to speech'; }
  return b;
}

function addButtons() {
  for (const buttons of document.querySelectorAll('#chat .message-buttons-left')) {
    const wrap = buttons.querySelector('.icon-button-wrapper');
    if (!wrap || wrap.querySelector('.msg-help-btn') || !rowOf(buttons)) continue;
    wrap.append(listenButton(), button('translate', 'Translate to English'), button('words', 'Explain words from this message'));
  }
}
if (synth) synth.getVoices();  // start loading the voice list
new MutationObserver(addButtons).observe(document.body, { childList: true, subtree: true });
addButtons();
"""


def buttons_script() -> tuple[gr.Textbox, gr.Button]:
    """Put in the Chat tab: an invisible element whose script adds the buttons to the chat's
    messages, and the hidden textbox and button the script sends a message through. They sit
    here, not in the side panel, because a closed panel's contents aren't on the page."""
    icons = json.dumps({"listen": LISTEN_ICON, "stop": STOP_ICON, "translate": TRANSLATE_ICON, "words": WORDS_ICON})
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
