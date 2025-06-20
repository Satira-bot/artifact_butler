import streamlit as st
from pathlib import Path

import src.utils.helpers as h
from src.pages.help_page import render_help_page
from src.pages.optimization_page import optimization_page
from src.pages.calculator_page import manual_calculator_page
from src.pages.collection_page import collection_page
from src.ui.components import render_header


def main() -> None:
    st.set_page_config(
        page_title="Артефактный Лакей",
        page_icon='assets/favicon.png',
        layout="wide",
        initial_sidebar_state="expanded"
    )

    css = Path("assets/styles.css").read_text()
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

    render_header()

    params = st.query_params
    if "build" in params:
        st.session_state["page"] = "Калькулятор"

    with st.sidebar:
        st.markdown(
            "<div style='padding: 20px 10px 10px;'><h2 style='margin: 0; font-size: 28px;'>Навигация</h2></div>",
            unsafe_allow_html=True
        )
        st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)

        if st.button("🎯 Найди свой билд", key="nav_opt"):
            st.session_state["page"] = "Оптимизация сборок"
        if st.button("🎒 Собери сам", key="nav_calc"):
            st.session_state["page"] = "Калькулятор"
        if st.button("🧾 Коллекция Лакея", key="nav_builds"):
            st.session_state["page"] = "Коллекция Лакея"
        if st.button("🎩 Пособие Лакея", key="nav_help"):
            st.session_state["page"] = "Инструкция"
        if st.button("📖 О проекте", key="nav_about"):
            st.session_state["page"] = "О проекте"

    page = st.session_state.get("page", "Оптимизация сборок")

    if page == "Оптимизация сборок":
        optimization_page()
    elif page == "Калькулятор":
        manual_calculator_page()
    elif page == "Коллекция Лакея":
        collection_page()
    elif page == "О проекте":
        readme = Path("README.md").read_text(encoding="utf-8")
        st.markdown(readme, unsafe_allow_html=True)
    elif page == "Инструкция":
        render_help_page()

    st.markdown(f"""
    <hr class="site-footer-hr">
    <div class="site-footer">
      {h.get_random_footer_phrase()} — <b>hailSolus</b>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
