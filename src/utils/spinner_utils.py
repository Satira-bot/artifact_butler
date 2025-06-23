import time
import threading
import streamlit as st
import streamlit.components.v1 as components
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

from src.utils.helpers import get_base64_image
from src.utils.constants import spinner_phrases


def get_spinner_html(phrases: list[str]) -> str:
    spinner_img = get_base64_image("assets/spinner.png")

    return f"""
    <div style="display:flex; align-items:center; gap:16px; height:100px;">
      <img
        src="data:image/png;base64,{spinner_img}"
        class="spinner" width="90" height="90"
      />
      <h4 id="phrase" class="typewriter"></h4>
    </div>

    <style>
      @keyframes spin {{
        from {{ transform: rotate(0deg); }}
        to   {{ transform: rotate(360deg); }}
      }}
      .spinner {{
        display:inline-block;
        transform-origin:center center;
        animation: spin 3.5s linear infinite;
      }}
      @keyframes fadeUpHoldDown {{
      0% {{
        opacity: 0;
        transform: translateY(-8px);
      }}
      30%, 70% {{
        opacity: 1;
        transform: none;
      }}
      100% {{
        opacity: 0;
        transform: translateY(8px);
      }}
    }}        
    .typewriter {{
      display: inline-block;
      position: relative;
      overflow: hidden;
      white-space: normal;
      word-break: break-word;
      overflow-wrap: anywhere;
      line-height: 1.6;
      min-height: 24px;
      font-family: "Source Sans Pro", sans-serif;
      font-size: 19px;
      color: #eaeaea;    
      transform-origin: top;
      opacity: 0;
      animation: fadeUpHoldDown 3.5s ease-out infinite;
    }}
    </style>

    <script>
      const phrases = {phrases};
      const phraseEl = document.getElementById('phrase');
      let lastIndex = -1;
    
      function pick() {{
        let index;
        do {{
          index = Math.floor(Math.random() * phrases.length);
        }} while (index === lastIndex);
    
        lastIndex = index;
        phraseEl.innerText = phrases[index];
      }}
    
      pick();
      setInterval(pick, 3500);
    </script>
    """


def run_with_dynamic_spinner(task_fn, *args, **kwargs):
    placeholder = st.empty()

    with placeholder:
        components.html(
            get_spinner_html(spinner_phrases),
            height=120,
            scrolling=False
        )

    result = None
    done = False

    def task_wrapper():
        nonlocal result, done
        result = task_fn(*args, **kwargs)
        done = True

    thread = threading.Thread(target=task_wrapper)
    add_script_run_ctx(thread, get_script_run_ctx())
    thread.start()

    while not done:
        time.sleep(3.5)

    placeholder.empty()
    return result
