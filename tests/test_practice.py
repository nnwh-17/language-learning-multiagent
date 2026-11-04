"""The Practice page: a drawing box and a typing box, with no agents behind them."""

import gradio as gr

from jplearn import practice


def _components():
    with gr.Blocks() as page:
        practice.build()
    return page, {c.elem_id: c for c in page.blocks.values() if getattr(c, "elem_id", None)}


def test_page_has_a_drawing_box_and_a_plain_typing_box():
    page, components = _components()

    assert "<canvas" in components["kanji-pad"].value
    assert isinstance(components["typing-pad"], gr.Textbox)
    assert not page.fns  # everything runs in the browser: no events, no model calls


def test_pen_is_down_while_a_is_held_with_a_toggle_for_click_and_drag():
    js = practice.DRAW_JS
    assert practice.PEN_KEY == "KeyA"
    assert "const KEY = 'KeyA', KEY_LABEL = 'A', WIDTH = 4;" in js
    assert "addEventListener('keydown'" in js and "addEventListener('keyup'" in js
    assert "let keyMode = true;" in js  # hold-A is the default
    assert "keyMode = !keyMode" in js  # the toggle switches to click and drag
    assert 'class="pad-mode"' in practice.DRAW_HTML


def test_practice_page_is_mounted_on_the_web_app():
    from jplearn.web import demo

    assert ("practice", "Practice") in {(path, name) for path, name, _in_navbar in demo.pages}
