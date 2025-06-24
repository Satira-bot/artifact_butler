import json
import pandas as pd
import streamlit as st
from typing import Dict, List, Any

from src.utils.constants import BUILDS_FILE, BASE_URL
from src.utils.helpers import calculate_table_height
from src.pages.calculator_page import (
    load_artifacts,
    df_from_encoded_build,
    calc_summary_df,
    assemble_metrics_df,
    style_metrics_html,
)


def _load_builds_by_slots() -> Dict[int, List[Dict[str, Any]]]:
    """
    Читаем и приводим ключи к int; если нет файла - возвращаем пустой словарь.
    """
    if not BUILDS_FILE.exists():
        st.warning(f"Файл с коллекцией билдов не найден: {BUILDS_FILE.as_posix()}")
        return {}

    try:
        raw: Dict[str, List[Dict[str, Any]]] = json.loads(BUILDS_FILE.read_text(encoding="utf-8"))
        return {int(k): v for k, v in raw.items()}
    except Exception as exc:
        st.error(f"Не удалось разобрать {BUILDS_FILE.name}: {exc}")
        return {}


def _render_build_tab(build: Dict[str, Any], art_data: Dict[str, Dict[str, Dict[str, float]]]) -> None:
    """
    Отрисовка одной вкладки витрины.
    """
    try:
        df: pd.DataFrame = df_from_encoded_build(build["encoded"])
    except Exception as exc:
        st.error(f"❌ Не удалось декодировать билд {build.get('id', 'WTF???')}: {exc}")
        return

    st.markdown(
        "<div style='text-align: right; font-size: 14px; color: gray;'>"
        f"📎 Источник: {build.get('author', '—')}  "
        "</div><br>",
        unsafe_allow_html=True
    )

    _, left_col, right_col, _ = st.columns([0.6, 1, 1, 0.6], gap="large")

    with left_col:
        st.data_editor(
            df,
            hide_index=True,
            use_container_width=True,
            key=f"build_editor_{build['id']}",
            height=calculate_table_height(df),
            column_config={
                "Артефакт": st.column_config.TextColumn("Артефакт", disabled=True),
                "Тир": st.column_config.NumberColumn("Тир", disabled=True),
                "Количество": st.column_config.NumberColumn("Количество", disabled=True),
            },
        )

    with right_col:
        summary = calc_summary_df(df, art_data)
        df_metrics = assemble_metrics_df(summary, df, art_data)
        st.markdown(style_metrics_html(df_metrics), unsafe_allow_html=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    calc_url = f"{BASE_URL}?build={build['encoded']}"
    placeholder = st.empty()
    _, left_btn, right_btn, _ = st.columns([0.6, 1, 1, 0.6], gap="small")

    with left_btn:
        if st.button("📤 Поделиться", key=f"share_{build['id']}", use_container_width=True):
            full_url = calc_url
            placeholder.success("Персональная ссылка от Лакея")
            placeholder.code(full_url, language="markdown", wrap_lines=True)

    with right_btn:
        st.link_button(
            label="🧮 Открыть в калькуляторе",
            url=calc_url,
            type="secondary",
            use_container_width=True,
        )


def collection_page() -> None:
    st.subheader("🧾 Коллекция Лакея")

    with st.expander("✨ Немного вдохновения, пара удачных находок и щепотка безумия", expanded=False):
        st.markdown("""        
        🧷 *Ты на особой странице, где Лакей хранит билды.*  
        Не спрашивай, зачем ему столько — возможно, это его способ бороться с экзистенциальным кризисом. Или он просто не умеет оставлять хаос без подписи.
        
        ---
        
        - ✅ Здесь ты найдёшь сборки, которые кто-то когда-то сделал, проверил и решил: *«Ого, а это ведь неплохо!»*
        
        - 🎲 Некоторые билды получились случайно, другие — стали итогом глубоких размышлений.  
          Но все они здесь, потому что **заслуживают внимания**.
        
        - 📎 Многие из представленных сборок родом из Discord-канала **FURY**, что уютно обосновался на сервере **NH5**.  
          Спасибо, Sakura, за то, что не только сохранила эти билды, но и сама внесла в них смысл и внимание — без тебя коллекция была бы пустой. Ты прекрасна.

        ---

        🤝 А если вдруг в какой-то сборке ты узнаешь себя — не удивляйся.  
        С хорошими билдами всегда так: **смотришь на них, а они смотрят в ответ.**
        """)

    st.divider()

    builds_by_slots = _load_builds_by_slots()
    if not builds_by_slots:
        st.info("Пока нет загруженных коллекций билдов. Загляни позже!")
        return

    slot_options = sorted(builds_by_slots)
    slots_sel = st.selectbox(
        "🔢 Выбери количество артефактов",
        options=slot_options,
        format_func=lambda x: f"{x} шт.",
    )

    builds = builds_by_slots.get(slots_sel, [])
    if not builds:
        st.warning("Нет билдов с таким количеством артефактов.")
        return

    tab_titles = [b.get("id", f"Build {i + 1}") for i, b in enumerate(builds)]
    tabs = st.tabs(tab_titles)

    art_data = load_artifacts()

    for tab, build in zip(tabs, builds):
        with tab:
            _render_build_tab(build, art_data)
