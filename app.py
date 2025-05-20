import json
import pandas as pd
import streamlit as st
from pathlib import Path

import src.utils.helpers as h
from src.logic.optimizer import compute_builds
from src.logic.exporter import ExcelExporter
from src.utils.spinner_utils import run_with_dynamic_spinner
from src.ui.components import display_results, render_header
from src.utils.constants import preset_map, build_label_alt, build_label_det


def optimization_page() -> None:
    settings = h.Settings()

    presets = ["(по умолчанию)"] + list(preset_map.keys())
    sel = st.selectbox("Пресет ранга", presets, index=0, key="rank_preset")

    if sel in preset_map:
        cfg = preset_map[sel]
        settings.tier = cfg["tier"]
        settings.num_slots = cfg["num_slots"]
        settings.blacklist = cfg["blacklist"]
        settings.max_copy = cfg["max_copy"]

    with st.form("opt_form", clear_on_submit=False):
        st.subheader("⚙️ Основные параметры")
        c1, c2 = st.columns(2, gap="large")
        with c1:
            settings.num_slots = st.number_input(
                "Слотов", 1, 24, settings.num_slots, key="slots_basic"
            )
            settings.max_copy = st.number_input(
                "Максимум копий артефакта", 1, 5, settings.max_copy, key="max_copy_basic",
                help="Указывает, сколько раз один и тот же артефакт может использоваться в сборке."
            )
        with c2:
            settings.tier = st.number_input(
                "Тир", 1, 4, settings.tier, key="tier_basic"
            )
            bl_raw = st.text_input(
                "Исключить (через запятую)",
                ", ".join(settings.blacklist),
                help="Список артефактов, которые не будут использоваться при подборе сборки. Например: «Душа, Пустышка» (без кавычек).",
                key="blacklist_basic"
            )

        with st.expander("🔧 Расширенные настройки свойств", expanded=False):
            props = h.Props.load(
                f"props/props_tier{settings.tier}.yaml",
                settings.num_slots
            )
            x1, x2 = st.columns(2, gap="large")
            with x1:
                settings.alt_cnt = st.number_input(
                    "Количество альтернатив", 0, 20,
                    value=settings.alt_cnt, step=1,
                    help="Сколько альтернативных билдов генерировать"
                )
            with x2:
                settings.alt_jitter = st.number_input(
                    "Варьируем приоритеты", 0.0, 1.0,
                    value=settings.alt_jitter, step=0.01,
                    help="Насколько сильно варьировать при построении альтернатив"
                )

            settings.recompute()

            df = h.props_to_df(props)
            df_editor = st.data_editor(
                df, num_rows="fixed", hide_index=True, use_container_width=True,
                column_config={
                    "Use": st.column_config.CheckboxColumn(
                        "Учитываем",
                        help='Включите, если это свойство должно влиять на подбор артефактов.'),
                    "Property": st.column_config.TextColumn(
                        "Свойство", disabled=True,
                        help='Название свойства артефакта (например, еда, вода, радиация).'),
                    "Priority": st.column_config.NumberColumn(
                        "Приоритет",
                        help='Насколько важно это свойство при подборе. Чем выше, тем сильнее влияет на итоговую сборку.',
                        max_value=10),
                    "Min enabled": st.column_config.CheckboxColumn(
                        "Вкл. нижнюю границу?",
                        help='Ограничить минимальное значение свойства для поиска сборок.'),
                    "Min": st.column_config.NumberColumn(
                        "Нижняя граница", step=1,
                        help='Минимально допустимое значение свойства в сборке.',
                        max_value=100),
                    "Max enabled": st.column_config.CheckboxColumn(
                        "Вкл. верхнюю границу?",
                        help='Ограничить максимальное значение свойства для поиска сборок.'),
                    "Max": st.column_config.NumberColumn(
                        "Верхняя граница",
                        help='Максимально допустимое значение свойства в сборке.',
                        max_value=1000),
                },
                key="adv_editor"
            )

            st.session_state["adv_df"] = df_editor

        submitted = st.form_submit_button("🚀 Запустить подбор")

    if submitted:

        data_path = Path("data/artifacts_data.json")
        all_artifacts = []

        if data_path.exists():
            art_data = json.loads(data_path.read_text(encoding="utf-8"))
            all_artifacts = list(art_data.keys())

        raw_items, info_msg = h.normalize_blacklist_input(bl_raw)
        if info_msg:
            st.info(info_msg)

        valid, invalid = h.validate_blacklist(raw_items, all_artifacts)
        if invalid:
            st.error(
                f"О, как печально... Артефакты с именами {', '.join(invalid)} не были найдены. "
                "Возможно, вы допустили ошибку в написании или забыли использовать запятую в качестве разделителя. "
            )
            return

        settings.blacklist = valid

        df2 = st.session_state.get("adv_df")
        if df2 is None:
            st.error("Не удалось прочитать расширенные настройки")
            return

        h.df_to_props(df2, props)

        errors = h.validate_adv_props(df2)
        if errors:
            for e in errors:
                st.error(e)
            return

        st.info("О, великолепно! Все параметры аккуратно сохранены")

        best, alts = run_with_dynamic_spinner(compute_builds, props, settings)

        st.session_state["best"] = best
        st.session_state["alts"] = alts
        st.session_state["show_builds"] = True

    if st.session_state.get("show_builds"):
        best = st.session_state["best"]
        alts = st.session_state["alts"]
        props_final = h.Props.load(f"props/props_tier{settings.tier}.yaml", settings.num_slots)

        display_results(best, alts, props_final)

        btn_cols = st.columns([1.3, 1, 1.1, 1, 1, 1])

        choice = btn_cols[0].selectbox(
            "Билд",
            [build_label_det] + [f"{build_label_alt} {a['run']}" for a in alts],
            key="result_build_choice",
            label_visibility="collapsed"
        )

        if btn_cols[1].button("Показать билд ниже", key="show_build_button"):
            st.session_state["show_table"] = True

        build_map = {
            f"{build_label_det}": best.get("build", {}),
            **{f"{build_label_alt} {a['run']}": a.get("build", {}) for a in alts}
        }
        build = build_map[choice]

        txt = "\n".join(f"{k}\t{v}" for k, v in build.items())
        btn_cols[2].download_button(
            "Сохранить билд в TXT",
            txt,
            file_name=f"build_{choice.lower().replace(' ', '_')}.txt",
            mime="text/plain"
        )

        exporter = ExcelExporter(settings, list(props_final.data.keys()))
        excel_bytes = exporter.build_bytes(best, alts)
        btn_cols[4].download_button(
            "Сохранить всё в Excel",
            excel_bytes,
            file_name="comparison_builds.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        if btn_cols[5].button("Сбросить результаты", key="reset_button"):
            for k in ("best", "alts", "show_builds", "show_table"):
                st.session_state.pop(k, None)
            st.rerun()

        if st.session_state.get("show_table", False):
            df_build = pd.DataFrame(build.items(), columns=["Артефакт", "Количество"])
            st.table(df_build)


def main() -> None:
    st.set_page_config(
        page_title="Артефактный лакей",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    css = Path("assets/styles.css").read_text()
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

    render_header()

    with st.sidebar:
        st.markdown(
            "<div style='padding: 20px 10px 10px;'><h2 style='margin: 0; font-size: 28px;'>Навигация</h2></div>",
            unsafe_allow_html=True
        )
        st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)

        if st.button("🏹 Оптимизация сборок", key="nav_opt"):
            st.session_state["page"] = "Оптимизация сборок"
        if st.button("📖 О проекте", key="nav_about"):
            st.session_state["page"] = "О проекте"

    page = st.session_state.get("page", "Оптимизация сборок")

    if page == "Оптимизация сборок":
        optimization_page()
    elif page == "О проекте":
        readme = Path("README.md").read_text(encoding="utf-8")
        st.markdown(readme, unsafe_allow_html=True)

    st.markdown(f"""
    <hr class="site-footer-hr">
    <div class="site-footer">
      {h.get_random_footer_phrase()} — <b>HailSolus</b>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
