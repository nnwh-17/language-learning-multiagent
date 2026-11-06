"""The Listen bar: text to speech in the browser, with no model or package behind it."""

import gradio as gr

from jplearn import speech


def _bar(**kwargs):
    with gr.Blocks() as page:
        bar = speech.speak_bar(["#a textarea", "#b"], **kwargs)
    return page, bar


def test_bar_runs_in_the_browser_with_the_web_speech_api():
    page, bar = _bar()

    assert not page.fns  # no Python events, so no server or model calls
    assert "speechSynthesis" in bar.js_on_load
    assert "SpeechSynthesisUtterance" in bar.js_on_load


def test_sources_and_language_are_passed_to_the_script():
    _, bar = _bar(lang="en-US", elem_id="x")

    assert 'const SOURCES = ["#a textarea", "#b"], LANG = "en-US";' in bar.js_on_load
    assert bar.elem_id == "x"


def test_speed_choices_default_to_a_learner_pace():
    _, bar = _bar()

    assert f'<option value="{speech.DEFAULT_RATE}" selected>' in bar.value
    assert bar.value.count("×</option>") == len(speech.RATES)
