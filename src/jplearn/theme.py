"""Gradio theme and CSS for the web UI: warm neutrals and a terracotta accent.

Colours of the agents panel and activity log live next to their renderers, in
``architecture.py`` and ``log_view.py``.
"""

import gradio as gr

THEME = gr.themes.Base(
    primary_hue="orange",
    neutral_hue="stone",
    radius_size="lg",
    font=[
        "Bold Hiragana", "ui-sans-serif", "-apple-system", "Segoe UI", "Hiragino Sans", "Yu Gothic UI", "Meiryo",
        "sans-serif",
    ],
    font_mono=["ui-monospace", "Cascadia Code", "Consolas", "monospace"],
).set(
    body_background_fill="#faf9f5",
    body_background_fill_dark="#262624",
    background_fill_primary="#faf9f5",
    background_fill_primary_dark="#262624",
    background_fill_secondary="#f5f4ed",
    background_fill_secondary_dark="#1f1e1d",
    block_background_fill="#ffffff",
    block_background_fill_dark="#30302e",
    block_border_color="#e8e6dc",
    block_border_color_dark="#3e3e38",
    border_color_primary="#e8e6dc",
    border_color_primary_dark="#3e3e38",
    block_shadow="none",
    block_shadow_dark="none",
    body_text_color="#141413",
    body_text_color_dark="#f5f4ef",
    body_text_color_subdued="#73726c",
    body_text_color_subdued_dark="#a6a39a",
    color_accent="#c96442",
    color_accent_soft="#f5e6de",
    color_accent_soft_dark="#4a3128",
    input_background_fill="#ffffff",
    input_background_fill_dark="#30302e",
    button_primary_background_fill="#c96442",
    button_primary_background_fill_dark="#c96442",
    button_primary_background_fill_hover="#b5583a",
    button_primary_background_fill_hover_dark="#d97757",
    button_primary_text_color="#ffffff",
    button_primary_text_color_dark="#ffffff",
    button_secondary_background_fill="transparent",
    button_secondary_background_fill_dark="transparent",
    button_secondary_background_fill_hover="#f0eee6",
    button_secondary_background_fill_hover_dark="#3a3a37",
)

SERIF = '"Bold Hiragana", ui-serif, Georgia, "Hiragino Mincho ProN", "Yu Mincho", serif'
CSS = f"""
/* Hiragana is much thinner than kanji at normal weight, so it gets a bold face of its own.
   unicode-range limits this font to hiragana; everything else falls through to the next
   font in the stack. Declared for all weights so the browser never fakes extra bold. */
@font-face {{ font-family: "Bold Hiragana"; font-weight: 100 900; unicode-range: U+3040-309F;
  src: local("Yu Gothic Bold"), local("YuGothic-Bold"), local("Hiragino Sans W6"), local("HiraginoSans-W6"),
       local("Meiryo Bold"), local("Meiryo-Bold"), local("Noto Sans JP Bold"), local("NotoSansJP-Bold"); }}

footer {{ display: none !important; }}
.gradio-container {{ max-width: 100% !important; }}

/* Centred conversation column, like claude.ai */
#main {{ max-width: 800px; width: 100%; margin: 0 auto; }}
#chat, #chat .bubble-wrap {{ border: none !important; background: transparent !important; }}
#chat .message {{ font-size: 16px; line-height: 1.65; }}
#chat .bot-row .message, #chat .message.bot {{
  background: transparent !important; border: none !important; box-shadow: none !important;
  font-family: {SERIF}; }}
#chat .user-row .message, #chat .message.user {{
  background: #f0eee6 !important; border: none !important; border-radius: 16px !important;
  padding: 10px 16px !important; }}
.dark #chat .user-row .message, .dark #chat .message.user {{ background: #141413 !important; }}
#chat .bubble.bot-row {{ max-width: 100%; }}
#chat .placeholder-content h2 {{ font-family: {SERIF}; font-weight: 400; font-size: 32px; }}

/* Rounded composer with the send button inside it */
#composer {{ border: 1px solid var(--border-color-primary) !important; border-radius: 20px !important;
  background: var(--input-background-fill) !important; padding: 10px 12px !important;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.04); }}
#composer textarea {{ font-size: 16px; background: transparent !important; border: none !important;
  box-shadow: none !important; }}
#composer button {{ background: #c96442 !important; color: white !important; border-radius: 10px !important; }}
#composer button:hover {{ background: #b5583a !important; }}
#chat .examples {{ grid-template-columns: repeat(2, 1fr) !important; max-width: 640px; margin: 0 auto; }}
.hint, .hint * {{ text-align: center; font-size: 12px !important; color: var(--body-text-color-subdued) !important; }}

/* Furigana above kanji */
#chat ruby rt {{ font-size: 0.55em; color: var(--body-text-color-subdued); }}
#chat .message {{ ruby-position: over; }}

/* Quiz panel: a card under the chat (or in Read & translate), one question at a time */
.quiz-panel {{ border: 1px solid var(--border-color-primary) !important; border-radius: 16px !important;
  background: var(--block-background-fill) !important; padding: 14px 16px !important; gap: 10px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.04); }}
.quiz-panel .quiz-head {{ display: flex; justify-content: space-between; gap: 12px; font-size: 13px;
  color: var(--body-text-color-subdued); }}
.quiz-panel .quiz-head b {{ color: var(--body-text-color); font-weight: 600; }}
.quiz-panel .quiz-bar {{ display: flex; gap: 4px; margin-top: 8px; }}
.quiz-panel .quiz-bar .step {{ flex: 1; height: 5px; border-radius: 3px; background: var(--border-color-primary); }}
.quiz-panel .quiz-bar .step.current {{ background: var(--color-accent); opacity: 0.45; }}
.quiz-panel .quiz-bar .step.right {{ background: #3f9a5b; }}
.quiz-panel .quiz-bar .step.wrong {{ background: #d1574b; }}
.quiz-question {{ font-size: 17px; line-height: 1.6; }}
.quiz-question h2 {{ font-family: {SERIF}; font-size: 34px; font-weight: 500; margin: 8px 0 0; }}
.quiz-choices .wrap {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px; }}
.quiz-choices label {{ border: 1px solid var(--border-color-primary) !important; border-radius: 10px !important;
  padding: 10px 14px !important; background: var(--background-fill-primary) !important; font-size: 15px; }}
.quiz-choices label.selected {{ border-color: var(--color-accent) !important;
  background: var(--color-accent-soft) !important; }}
.quiz-typed textarea {{ font-size: 17px; }}
.quiz-feedback {{ font-size: 15px; line-height: 1.6; }}
.quiz-actions {{ gap: 8px; justify-content: flex-end; }}
.quiz-actions button {{ flex: 0 0 auto; min-width: 120px; border-radius: 10px; }}

/* Read & translate tab */
#tabs {{ flex-grow: 1; }}
#chat-tab {{ display: flex; flex-direction: column; flex-grow: 1; }}
#reader-tab {{ gap: 12px; }}
#reader-tab h4 {{ font-family: {SERIF}; font-weight: 500; font-size: 20px; margin: 12px 0 0; }}
.hint-left, .hint-left * {{ font-size: 13px !important; color: var(--body-text-color-subdued) !important; }}
.reader-text, .reader-empty {{ font-family: {SERIF}; font-size: 22px; line-height: 2; padding: 14px 16px;
  border: 1px solid var(--border-color-primary); border-radius: 12px; background: var(--block-background-fill);
  white-space: pre-wrap; }}
.reader-empty {{ font-size: 15px; color: var(--body-text-color-subdued); }}
.reader-text .hl {{ background: #fde68a; border-radius: 3px; box-shadow: 0 2px 0 #f59e0b; }}
.reader-text .hl.mistake {{ background: #fecaca; box-shadow: 0 2px 0 #d1574b; }}
.dark .reader-text .hl {{ background: #6b5313; box-shadow: 0 2px 0 #f59e0b; }}
.dark .reader-text .hl.mistake {{ background: #6b2a24; box-shadow: 0 2px 0 #d1574b; }}
.hl-bar {{ display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; font-size: 13px;
  color: var(--body-text-color-subdued); }}
.hl-bar button {{ border: 1px solid var(--border-color-primary); border-radius: 8px; padding: 4px 10px;
  background: var(--block-background-fill); color: var(--body-text-color); cursor: pointer; font-size: 13px; }}
.hl-bar .hl-setkey {{ border: none; background: none; padding: 0; text-decoration: underline;
  color: var(--body-text-color-subdued); }}
.hl-bar kbd {{ border: 1px solid var(--border-color-primary); border-bottom-width: 2px; border-radius: 5px;
  padding: 0 6px; font-family: var(--font-mono); color: var(--body-text-color); }}
html:not([data-hl="on"]) .hl-bar .mode-on, html[data-hl="on"] .hl-bar .mode-off {{ display: none; }}
html[data-hl="on"] .hl-toggle {{ background: #fde68a; border-color: #f59e0b; color: #141413; }}
/* Highlighter cursor and selection colour while highlighting */
html[data-hl="on"] .reader-text {{ cursor: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24'><path d='M4 20l3-1 11-11-2-2L5 17z' fill='%23f59e0b' stroke='%23141413' stroke-width='1.2'/><path d='M3 21h7' stroke='%23f59e0b' stroke-width='3'/></svg>") 3 21, text;
  border-color: #f59e0b; }}
html[data-hl="on"] .reader-text ::selection {{ background: #fde68a; color: inherit; }}
html[data-hl="on"] .reader-text .hl {{ cursor: pointer; }}
.reader-clear {{ align-self: flex-start; }}
#reader-tab button.secondary {{ border: 1px solid var(--border-color-primary); }}
.reader-breakdown {{ font-size: 15px; line-height: 1.6; }}

#approval {{ gap: 8px; justify-content: center; }}
#approval button {{ max-width: 160px; border-radius: 10px; }}
#approval button.secondary {{ border: 1px solid var(--border-color-primary); }}

/* Sidebars */
.sidebar {{ background: var(--background-fill-secondary) !important; }}
.brand h2 {{ font-family: {SERIF}; font-weight: 500; margin: 4px 0 12px; }}
#new-chat {{ justify-content: flex-start; font-weight: 500; border: none; box-shadow: none; }}
.side-section {{ border: none !important; background: transparent !important; }}

/* Saved chats: a plain list, one line each, the open one highlighted */
#chats {{ border: none !important; background: transparent !important; padding: 0 !important; }}
#chats .wrap {{ display: flex; flex-direction: column; gap: 2px; }}
#chats label {{ width: 100%; border: none !important; background: transparent !important;
  box-shadow: none !important; padding: 6px 8px; border-radius: 8px; overflow: hidden; }}
#chats label span {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
#chats label.selected {{ background: var(--block-background-fill) !important; }}
#chats input[type=radio] {{ display: none; }}
#delete-chat {{ align-self: flex-start; font-size: 12px; border: none; box-shadow: none;
  color: var(--body-text-color-subdued); }}
"""
