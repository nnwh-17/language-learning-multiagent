"""Text to speech for the web UI, like the speaker button in an online translator.

It uses the browser's own speech engine (the Web Speech API, ``speechSynthesis``), so
there is no package to install, no model call and no server round trip: the voices are the
ones the operating system or browser provides (on Windows, add Japanese under Settings >
Time & language > Speech). ``speak_bar`` returns a small bar with Listen/Stop, a speed
setting and a voice picker that reads the text of another element on the page.

If text is selected inside that element, only the selection is read, so a learner can
select one word or sentence and hear it.
"""

import json

import gradio as gr

DEFAULT_RATE = 0.9  # a little slower than normal suits learners
RATES = [0.5, 0.75, 0.9, 1.0, 1.25]

SPEAK_HTML = """
<div class="tts-bar">
  <button type="button" class="tts-play" title="Listen (reads the selection, if any)">🔊 Listen</button>
  <label class="tts-field">Speed
    <select class="tts-rate">__RATES__</select>
  </label>
  <label class="tts-field">Voice
    <select class="tts-voice"><option value="">Default</option></select>
  </label>
  <span class="tts-note"></span>
</div>
"""

# Long texts are split into sentences and queued: some browsers stop a single long
# utterance after about 15 seconds.
SPEAK_JS = """
const SOURCES = __SOURCES__, LANG = __LANG__;
const synth = window.speechSynthesis;
const play = element.querySelector('.tts-play');
const rate = element.querySelector('.tts-rate');
const voicePick = element.querySelector('.tts-voice');
const note = element.querySelector('.tts-note');
const store = (k, v) => { try { v === undefined ? (v = localStorage.getItem(k)) : localStorage.setItem(k, v); } catch (e) { v = null; } return v; };
const VOICE_KEY = 'jplearn-tts-voice-' + LANG, RATE_KEY = 'jplearn-tts-rate';
let selected = '';  // text selected in the source when the button was pressed
let speaking = false;

if (!synth) {
  play.disabled = true;
  note.textContent = 'This browser has no text to speech.';
}

const saved = store(RATE_KEY);
if (saved) rate.value = saved;
rate.addEventListener('change', () => store(RATE_KEY, rate.value));
voicePick.addEventListener('change', () => store(VOICE_KEY, voicePick.value));

function voices() {
  const base = LANG.split('-')[0].toLowerCase();
  return synth.getVoices().filter((v) => v.lang.replace('_', '-').toLowerCase().startsWith(base));
}
function rank(v) {  // natural/online voices sound far better than the old desktop ones
  return /natural|online|neural|google/i.test(v.name) ? 0 : v.localService ? 1 : 2;
}
function listVoices() {
  if (!synth) return;
  const list = voices().sort((a, b) => rank(a) - rank(b));
  const keep = store(VOICE_KEY) || voicePick.value;
  voicePick.innerHTML = '';
  if (!list.length) voicePick.add(new Option('Default', ''));
  for (const v of list) voicePick.add(new Option(v.name.replace(/^Microsoft /, ''), v.voiceURI));
  if (list.some((v) => v.voiceURI === keep)) voicePick.value = keep;
  note.textContent = list.length ? '' : 'No ' + LANG + ' voice found: add one in your system speech settings.';
}

function source() {
  for (const s of SOURCES) {
    const el = document.querySelector(s);
    if (el && el.offsetParent !== null) return el;
  }
  return null;
}
function textOf(el) {
  return ('value' in el && typeof el.value === 'string') ? el.value : el.innerText;
}
function selectionIn(el) {
  if ('selectionStart' in el && typeof el.value === 'string') {
    return el.value.slice(el.selectionStart, el.selectionEnd);
  }
  const sel = window.getSelection();
  if (!sel.rangeCount || sel.isCollapsed) return '';
  const range = sel.getRangeAt(0);
  return el.contains(range.commonAncestorContainer) ? sel.toString() : '';
}
function chunks(text) {
  return (text.match(/[^。！？!?.\\n]+[。！？!?.]*/g) || []).map((s) => s.trim()).filter(Boolean);
}
function show(on) {
  speaking = on;
  play.textContent = on ? '⏹ Stop' : '🔊 Listen';
  element.classList.toggle('tts-speaking', on);
}

// Remember the selection before the click can clear it
play.addEventListener('pointerdown', () => { const el = source(); selected = el ? selectionIn(el) : ''; });
play.addEventListener('click', (e) => {
  e.currentTarget.blur();
  if (speaking || synth.speaking) { synth.cancel(); show(false); return; }
  const el = source();
  const text = (selected || (el ? selectionIn(el) : '') || (el ? textOf(el) : '')).trim();
  selected = '';
  if (!text) { note.textContent = 'Nothing to read yet.'; return; }
  listVoices();
  const voice = voices().find((v) => v.voiceURI === voicePick.value);
  const parts = chunks(text);
  synth.cancel();  // one voice at a time, across every bar on the page
  parts.forEach((part, i) => {
    const u = new SpeechSynthesisUtterance(part);
    u.lang = voice ? voice.lang : LANG;
    if (voice) u.voice = voice;
    u.rate = +rate.value;
    if (i === parts.length - 1) { u.onend = () => show(false); }
    u.onerror = () => show(false);
    synth.speak(u);
  });
  show(true);
});

if (synth) {
  listVoices();
  synth.addEventListener('voiceschanged', listVoices);
}
"""


def speak_bar(sources: list[str], lang: str = "ja-JP", elem_id: str | None = None) -> gr.HTML:
    """A Listen bar that reads the first visible element matching one of ``sources``.

    ``sources`` are CSS selectors tried in order, e.g. the reading pane and then the text
    box it came from. A textarea or input is read by its value, anything else by its text.
    """
    rates = "".join(
        f'<option value="{r}"{" selected" if r == DEFAULT_RATE else ""}>{r}×</option>' for r in RATES
    )
    js = SPEAK_JS.replace("__SOURCES__", json.dumps(sources)).replace("__LANG__", json.dumps(lang))
    return gr.HTML(
        SPEAK_HTML.replace("__RATES__", rates),
        js_on_load=js,
        elem_id=elem_id,
        elem_classes="tts",
        container=False,
    )
