"""The web UI's Practice page: free writing and typing practice, no agents involved.

Both boxes run entirely in the browser: nothing calls a model or is saved. ``web.py``
mounts the page at ``/practice``.

- Writing: a canvas with two pen modes, switched by a toggle. "Hold A" (the default) puts the
  pen down only while ``PEN_KEY`` is held, so you draw by moving the mouse; "Click & drag" is
  normal drawing. Touch and stylus always draw on contact, since they have no key to hold.
- Typing: a plain text box.
"""

import gradio as gr

PEN_KEY = "KeyA"  # KeyboardEvent.code of the key that puts the pen down
PEN_KEY_LABEL = "A"
PEN_WIDTH = 4  # stroke width in CSS pixels

DRAW_HTML = """
<div class="pad-toolbar">
  <span class="pad-status"></span>
  <span class="pad-buttons">
    <button type="button" class="pad-mode" aria-pressed="true"></button>
    <button type="button" class="pad-undo">↶ Undo</button>
    <button type="button" class="pad-clear">Clear</button>
  </span>
</div>
<canvas class="pad-canvas" aria-label="Kanji writing area"></canvas>
"""

DRAW_JS = """
const KEY = '__PEN_KEY__', KEY_LABEL = '__PEN_KEY_LABEL__', WIDTH = __PEN_WIDTH__;
const canvas = element.querySelector('.pad-canvas');
const ctx = canvas.getContext('2d');
const status = element.querySelector('.pad-status');
const modeButton = element.querySelector('.pad-mode');
const strokes = [];  // each stroke is a list of {x, y} in CSS pixels
let keyMode = true;  // true: hold the key to draw; false: click and drag
let current = null, penDown = false, inside = false, pos = null;

// The page can be loaded more than once (e.g. switching pages): drop the old key listeners
if (window.__kanjiPad) window.__kanjiPad.abort();
const control = new AbortController();
window.__kanjiPad = control;
const opts = { signal: control.signal };

const ink = () => getComputedStyle(element).getPropertyValue('--body-text-color').trim() || '#141413';
const point = (e) => { const r = canvas.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };

function style() {
  ctx.strokeStyle = ink(); ctx.lineWidth = WIDTH; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
}
function drawStroke(s) {
  style(); ctx.beginPath(); ctx.moveTo(s[0].x, s[0].y);
  if (s.length === 1) ctx.lineTo(s[0].x + 0.01, s[0].y);  // a dot
  for (const p of s.slice(1)) ctx.lineTo(p.x, p.y);
  ctx.stroke();
}
function redraw() {
  const r = canvas.getBoundingClientRect();
  ctx.clearRect(0, 0, r.width, r.height);
  strokes.forEach(drawStroke);
}
function resize() {  // keep the canvas sharp at its displayed size
  const dpr = window.devicePixelRatio || 1, r = canvas.getBoundingClientRect();
  canvas.width = Math.round(r.width * dpr); canvas.height = Math.round(r.height * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  redraw();
}
function begin(p) { current = [p]; strokes.push(current); drawStroke(current); }
function extend(p) {
  const last = current[current.length - 1];
  current.push(p);
  style(); ctx.beginPath(); ctx.moveTo(last.x, last.y); ctx.lineTo(p.x, p.y); ctx.stroke();
}
function end() { current = null; }
function show() {
  element.classList.toggle('pen-down', penDown);
  modeButton.textContent = keyMode ? `⌨️ Hold ${KEY_LABEL}` : '🖱️ Click & drag';
  modeButton.setAttribute('aria-pressed', String(keyMode));
  status.innerHTML = penDown ? '✏️ Pen down'
    : keyMode ? `Hold <kbd>${KEY_LABEL}</kbd> and move the mouse to draw`
    : 'Click and drag to draw';
}
function typing() {
  const a = document.activeElement;
  return a && (a.tagName === 'TEXTAREA' || a.tagName === 'INPUT' || a.isContentEditable);
}

// Hold-key mode: the key works anywhere on the page, except while typing in a text box
document.addEventListener('keydown', (e) => {
  if (!keyMode || e.code !== KEY || typing() || e.ctrlKey || e.metaKey || e.altKey) return;
  e.preventDefault();
  if (e.repeat || penDown) return;
  penDown = true;
  if (inside && pos) begin(pos);
  show();
}, opts);
document.addEventListener('keyup', (e) => {
  if (e.code !== KEY || !penDown) return;
  e.preventDefault();
  penDown = false; end(); show();
}, opts);
window.addEventListener('blur', () => { penDown = false; end(); show(); }, opts);

canvas.addEventListener('pointerenter', (e) => { inside = true; pos = point(e); if (penDown) begin(pos); });
canvas.addEventListener('pointermove', (e) => { pos = point(e); if (current) extend(pos); });
canvas.addEventListener('pointerleave', () => { inside = false; if (keyMode) end(); });
// Click-and-drag mode for the mouse; touch and stylus always draw while touching
canvas.addEventListener('pointerdown', (e) => {
  if (e.pointerType === 'mouse' && (keyMode || e.button !== 0)) return;
  e.preventDefault();
  canvas.setPointerCapture(e.pointerId); begin(point(e));
  if (e.pointerType === 'mouse') { penDown = true; show(); }
});
canvas.addEventListener('pointerup', (e) => {
  if (e.pointerType === 'mouse' && keyMode) return;
  end();
  if (e.pointerType === 'mouse') { penDown = false; show(); }
});

modeButton.addEventListener('click', (e) => {
  keyMode = !keyMode; penDown = false; end(); show(); e.currentTarget.blur();
});
element.querySelector('.pad-undo').addEventListener('click', (e) => { strokes.pop(); redraw(); e.currentTarget.blur(); });
element.querySelector('.pad-clear').addEventListener('click', (e) => { strokes.length = 0; redraw(); e.currentTarget.blur(); });

new ResizeObserver(resize).observe(canvas);
show();
""".replace("__PEN_KEY__", PEN_KEY).replace("__PEN_KEY_LABEL__", PEN_KEY_LABEL).replace("__PEN_WIDTH__", str(PEN_WIDTH))


def build() -> None:
    """Lay out the page inside the current Blocks or route."""
    with gr.Column(elem_id="practice"):
        gr.Markdown("## Practice", elem_classes="brand")

        gr.Markdown("### ✍️ Write kanji")
        gr.HTML(DRAW_HTML, js_on_load=DRAW_JS, elem_id="kanji-pad", container=False)

        gr.Markdown("### ⌨️ Type")
        gr.Textbox(
            elem_id="typing-pad",
            show_label=False,
            lines=6,
            max_lines=20,
            placeholder="ここに入力してください… (type here)",
        )
