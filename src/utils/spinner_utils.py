import time
import random
import threading
import streamlit as st
import streamlit.components.v1 as components
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

from src.utils.constants import spinner_phrases


def get_random_spinner_phrase() -> str:
    """Возвращает случайную фразу для спиннера."""
    return random.choice(spinner_phrases)


def get_spinner_html(phrase: str) -> str:
    """Возвращает HTML со спиннером"""
    typing_speed = 0.04
    min_typing_duration = 0.5
    duration = max(len(phrase) * typing_speed, min_typing_duration)

    return f"""
    <div style='display: flex; align-items: center; gap: 16px;'>
        <div style='font-size:48px; animation:spin 2s linear infinite;'>☢️</div>
        <h4 class="typewriter">{phrase}</h4>
    </div>
    <style>
    @keyframes spin {{
      from {{ transform: rotate(0deg); }}
      to   {{ transform: rotate(360deg); }}
    }}

    @keyframes typing {{
      to {{ clip-path: inset(0 0 0 0); }}
    }}

    @keyframes blink {{
      50% {{ border-color: transparent; }}
    }}

    .typewriter {{
      display: inline-block;
      position: relative;
      overflow: hidden;
      white-space: nowrap;

      font-family: 'Source Code Pro', Consolas, 'Courier New', monospace;
      font-size: 20px;
      line-height: 1.4;
      color: #ffffff;

      clip-path: inset(0 100% 0 0);
      -webkit-clip-path: inset(0 100% 0 0);

      animation:
        typing {duration}s steps({len(phrase)}) forwards,
        blink 0.7s step-end infinite;
    }}
    </style>
    """


def run_with_dynamic_spinner(task_fn, *args, **kwargs):
    spinner_placeholder = st.empty()
    done = False
    result = None

    def task_wrapper():
        nonlocal result, done
        result = task_fn(*args, **kwargs)
        done = True

    thread = threading.Thread(target=task_wrapper)
    add_script_run_ctx(thread, get_script_run_ctx())
    thread.start()

    while not done:
        phrase = get_random_spinner_phrase()

        spinner_placeholder.empty()

        with spinner_placeholder:
            components.html(
                get_spinner_html(phrase),
                height=100,
                scrolling=False
            )

        time.sleep(3)

    spinner_placeholder.empty()
    return result
