import json
import base64
import pandas as pd
import streamlit as st
from pathlib import Path

import src.utils.helpers as h
from src.logic.exporter import ExcelExporter
from src.logic.optimizer import compute_builds
from src.utils.spinner_utils import run_with_dynamic_spinner
from src.ui.components import display_results
from src.utils.constants import preset_map, build_label_alt, build_label_det


def optimization_page() -> None:
    settings = h.Settings()
    presets = list(preset_map.keys())
    sel = st.selectbox("Пресет ранга", presets, index=0, key="rank_preset")
    data_path = Path("data/artifacts_data.json")
    all_artifacts = []

    if data_path.exists():
        art_data = json.loads(data_path.read_text(encoding="utf-8"))
        all_artifacts = list(art_data.keys())

    if sel in preset_map:
        cfg = preset_map[sel]
        settings.tier = cfg["tier"]
        settings.num_slots = cfg["num_slots"]
        settings.blacklist = cfg["blacklist"]
        settings.max_copy = cfg["max_copy"]
        settings.props_file = cfg["props_file"]

    all_rows = []
    for name in all_artifacts:
        for tier in (1, 2, 3, 4):
            all_rows.append({"Артефакт": name, "Тир": tier, "Количество": 0})
    df_all = pd.DataFrame(all_rows)

    if "fixed_artifacts" not in st.session_state:
        st.session_state.fixed_artifacts = []

    with st.expander("🔐 Обязательные артефакты в сборке", expanded=False):
        cols = st.columns([3, 1, 1])

        artifact_choice = cols[0].selectbox("Артефакт", options=all_artifacts, key="fixed_art")
        tier_choice = cols[1].selectbox("Тир", options=[1, 2, 3, 4], index=3, key="fixed_tier")

        with cols[2]:
            st.markdown("<div style='padding-top:28px;'></div>", unsafe_allow_html=True)
            if st.button("➕ Добавить", key="add_fixed"):
                st.session_state.fixed_artifacts.append((artifact_choice, tier_choice))

        if st.session_state.fixed_artifacts:
            st.markdown("**Текущий список: **")
            for idx, (name, tier) in enumerate(st.session_state.fixed_artifacts):
                line = st.columns([5, 1, 1])
                line[0].markdown(f"- **{name}**")
                line[1].markdown(f"Тир {tier}")
                if line[2].button("❌", key=f"remove_fixed_{idx}"):
                    st.session_state.fixed_artifacts.pop(idx)
                    st.rerun()

    with st.form("opt_form", clear_on_submit=False):
        st.subheader("⚙️ Основные параметры")
        c1, c2 = st.columns(2, gap="large")
        with c1:
            settings.num_slots = st.number_input(
                "Слотов", 3, 25, settings.num_slots, key="slots_basic"
            )
            settings.max_copy = st.number_input(
                "Максимум копий артефакта", 1, 5, settings.max_copy, key="max_copy_basic",
                help="Указывает, сколько раз один и тот же артефакт может использоваться в сборке."
            )
        with c2:
            settings.tier = st.number_input(
                "Тир", 1, 4, settings.tier, key="tier_basic"
            )
            selected_blacklist = st.multiselect(
                "Исключить артефакты",
                options=all_artifacts,
                default=settings.blacklist,
                help="Выберите из списка артефакты, которые не будут использоваться при подборе сборки.",
                key="blacklist_basic"
            )
            settings.blacklist = selected_blacklist

        with st.expander("🔧 Расширенные настройки свойств", expanded=False):
            props = h.Props.load(
                f"props/{settings.props_file}",
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
                        max_value=1000),
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
        df2 = st.session_state.get("adv_df")
        h.df_to_props(df2, props)

        errors = h.validate_all(df=df2,
                                fixed=st.session_state.fixed_artifacts,
                                num_slots=settings.num_slots,
                                max_copy=settings.max_copy)

        if errors:
            for e in errors:
                st.error(e)
            return

        st.toast("О, великолепно! Все параметры аккуратно сохранены", icon="💾")

        best, alts = run_with_dynamic_spinner(compute_builds, props, settings, st.session_state.fixed_artifacts)

        st.session_state["best"] = best
        st.session_state["alts"] = alts
        st.session_state["show_builds"] = True

    if st.session_state.get("show_builds"):
        best = st.session_state["best"]
        alts = st.session_state["alts"]
        props_final = h.Props.load(f"props/{settings.props_file}", settings.num_slots)

        display_results(best, alts, props_final)

        btn_cols = st.columns([1, 0.8, 0.9, 1.3, 1, 0.6])

        choice = btn_cols[0].selectbox(
            "Билд",
            [build_label_det] + [f"{build_label_alt} {a['run']}" for a in alts],
            key="result_build_choice",
            label_visibility="collapsed"
        )

        if btn_cols[1].button("Показать билд", key="show_build_button"):
            st.session_state["show_table"] = True

        build_map = {
            f"{build_label_det}": best.get("build", {}),
            **{f"{build_label_alt} {a['run']}": a.get("build", {}) for a in alts}
        }
        build = build_map[choice]
        build_list = [
            {
                "name": name,
                "tier": int(tier),
                "count": int(cnt)
            }
            for name, tier, cnt in build
        ]
        raw = json.dumps(build_list, ensure_ascii=False)
        encoded = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")
        share_href = f"/?build={encoded}"

        txt = "\n".join(
            f"{name}\t{tier}\t{cnt}"
            for name, tier, cnt in build
        )
        btn_cols[2].download_button(
            "Сохранить билд в TXT",
            txt,
            file_name=f"build_{choice.lower().replace(' ', '_')}.txt",
            mime="text/plain"
        )

        btn_cols[3].link_button(
            "Открыть билд в калькуляторе",
            url=share_href,
            type="secondary",
            use_container_width=True
        )

        exporter = ExcelExporter(settings, list(props_final.data.keys()))
        excel_bytes = exporter.build_bytes(best, alts)
        btn_cols[4].download_button(
            "Сохранить всё в Excel",
            excel_bytes,
            file_name="comparison_builds.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        if btn_cols[5].button("Сброс", key="reset_button"):
            for k in ("best", "alts", "show_builds", "show_table"):
                st.session_state.pop(k, None)
            st.rerun()

        if st.session_state.get("show_table", False):
            df_build = pd.DataFrame(
                build,
                columns=["Артефакт", "Тир", "Количество"]
            )
            st.table(df_build)

            with st.expander("🔍 Характеристики артефактов в билде", expanded=False):
                labels = []
                for name, tier, count in build:
                    stats = art_data[name][str(tier)]
                    if any(v != 0 for v in stats.values()):
                        labels.append(f"{name} T{tier}")

                if labels:
                    tabs = st.tabs(labels)
                    for (name, tier, count), tab in zip(
                            [(n, t, c) for n, t, c in build if f"{n} T{t}" in labels],
                            tabs):
                        stats = art_data[name][str(tier)]
                        filtered = {k: v for k, v in stats.items() if v != 0}
                        with tab:
                            df_stats = pd.DataFrame({
                                "Свойство": list(filtered.keys()),
                                "1 шт": [round(v, 2) for v in filtered.values()],
                                f"{count} шт": [round(v * count, 2) for v in filtered.values()],
                            })
                            st.dataframe(df_stats, use_container_width=True)
