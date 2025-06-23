import json
import base64
import math
import numpy as np
import pandas as pd
import streamlit as st
from pathlib import Path

import src.utils.helpers as h
from src.logic.exporter import ExcelExporter
from src.logic.optimizer import compute_builds
from src.utils.spinner_utils import run_with_dynamic_spinner
from src.utils.constants import preset_map, build_label_alt, build_label_det, ALIASES_DESCR_MAP


def draw_centered_slider_row(df_result: pd.DataFrame,
                             prop_list: list[str],
                             filter_vals: dict[str, float],
                             props: h.Props,
                             *,
                             prefix_key: str
                             ) -> None:
    """
    Рисует строку из слайдеров для фильтрации по выбранным свойствам.
    Если минимум и максимум совпадают — вместо слайдера показывается фиксированное значение.
    """
    cols = st.columns(7, gap="small")
    n = len(prop_list)
    left_pad = (7 - n) // 2

    for i, prop in enumerate(prop_list):
        col = cols[left_pad + i]
        lo = math.floor(float(df_result[prop].min()))
        hi = math.floor(float(df_result[prop].max()))
        label = f"{props.rus(prop)} ≥"

        if lo == hi:
            col.markdown(
                f"""
                    <div style="display:flex;align-items:center;justify-content:center;height:48px;">
                      <strong>{label} {lo}</strong>
                    </div>
                    """,
                unsafe_allow_html=True,
            )
            filter_vals[prop] = lo
        else:
            filter_vals[prop] = col.slider(
                label=label,
                min_value=lo,
                max_value=hi,
                value=lo,
                step=1,
                format="%d",
                key=f"{prefix_key}_{prop}",
            )


def display_results(best: dict, alts: list[dict], props: h.Props) -> None:
    """
    Строит тепловую карту результатов и два ряда фильтров-слайдеров.
    На экране используются русские названия свойств (`props.rus()`),
    а все расчёты ведутся по английским ключам.
    """
    if not best["build"]:
        st.error("О-о-о, какое разочарование! Подходящих сборок не найдено! "
                 "Быть может, слегка смягчите требования или проявите чуть больше гибкости в настройках?")
        return

    props_order = [k for k in props.data.keys() if k != "slots"]

    rows: list[dict] = []

    det = {"Type": build_label_det, "Run": None, "Score": best.get("score", 0.0)}
    det.update({k: best.get("stats", {}).get(k, 0.0) for k in props_order})
    rows.append(det)

    for a in alts:
        row = {
            "Type": f"{build_label_alt} {a.get('run', '')}",
            "Run": a.get("run"),
            "Score": a.get("score", 0.0),
            **{k: a.get(k, 0.0) for k in props_order},
        }
        rows.append(row)

    df_all = pd.DataFrame(rows)
    mask_nonzero = ~(df_all[props_order] == 0).all(axis=1)
    df_result = df_all[mask_nonzero]

    rus_order = [props.rus(k) for k in props_order]
    filter_vals: dict[str, float] = {}

    with st.expander("🔍 Параметры фильтрации", expanded=False):
        draw_centered_slider_row(df_result, props_order[:7], filter_vals, props, prefix_key="row1")

        if len(props_order) > 7:
            draw_centered_slider_row(df_result, props_order[7:], filter_vals, props, prefix_key="row2")

    if filter_vals:
        mask = np.logical_and.reduce([df_result[k] >= v for k, v in filter_vals.items()])
        df_filtered = df_result[mask]
    else:
        df_filtered = df_result

    if df_filtered.empty:
        st.error("Хм... Похоже, ни одна из сборок не проходит текущую фильтрацию. "
                 "Попробуйте ослабить ограничения, выставленные с помощью ползунков")
        return

    df_filtered_show = df_filtered.rename(columns=props.display).drop(columns=["Score", "Run"], errors="ignore")
    st.dataframe(
        df_filtered_show.style
        .format("{:.0f}", subset=df_filtered_show.columns.drop("Type"))
        .background_gradient(cmap="RdYlGn", subset=rus_order),
        use_container_width=True,
        height=min((len(df_filtered_show) + 1) * 35 + 5, 800),
    )


def optimization_page() -> None:
    settings = h.Settings()
    presets = list(preset_map.keys())
    sel = st.selectbox("Пресет ранга",
                       presets,
                       index=0,
                       key="rank_preset",
                       help="Определяет основные параметры и приоритеты свойств. Лакей шепчет: пробуй, экспериментируй, а вдруг найдёшь нечто удивительное.")
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
                "Максимум копий артефакта", 1, 10, settings.max_copy, key="max_copy_basic",
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
                height=30 + len(df) * 35 + 8,
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
        legend_container = st.empty()
        btn_cols = st.columns([0.8, 0.7, 0.75, 1.1, 0.75, 0.45, 0.3], gap="small")

        choice = btn_cols[0].selectbox(
            "Билд",
            [build_label_det] + [f"{build_label_alt} {a['run']}" for a in alts],
            key="result_build_choice",
            label_visibility="collapsed"
        )

        if btn_cols[1].button("👁️ Показать билд",
                              key="toggle_build_button",
                              help="Показать или скрыть состав выбранной сборки",
                              use_container_width=True):
            st.session_state["show_table"] = not st.session_state.get("show_table", False)
            st.rerun()

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
            f"{i + 1}. {name} (Тир {tier}) — {cnt} шт."
            for i, (name, tier, cnt) in enumerate(build)
        )
        btn_cols[2].download_button(
            "📝️ Сохранить в TXT",
            txt,
            file_name=f"build_{choice.lower().replace(' ', '_')}.txt",
            mime="text/plain",
            help="Сохранить список артефактов выбранного билда, сверстанный с заботой",
            use_container_width=True
        )

        btn_cols[3].link_button(
            "🧮️ Открыть билд в калькуляторе",
            url=share_href,
            type="secondary",
            use_container_width=True,
            help="Перейти в калькулятор с выбранной сборкой — чтобы рассмотреть всё в деталях"
        )

        exporter = ExcelExporter(settings, list(props_final.data.keys()))
        excel_bytes = exporter.build_bytes(best, alts)
        btn_cols[4].download_button(
            "📊️ Сохранить в Excel",
            excel_bytes,
            file_name="comparison_builds.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="Скачать сравнение всех сборок в Excel. Лакей любит таблицы",
            use_container_width=True
        )

        if btn_cols[5].button("♻️️ Сброс",
                              key="reset_button",
                              help="Очистить все сборки и начать с чистого КПК",
                              use_container_width=True):
            for k in ("best", "alts", "show_builds", "show_table"):
                st.session_state.pop(k, None)
            st.rerun()

        if st.session_state.get("show_table", False):
            tabs = st.tabs(["📋 Таблица", "📝 Текст"])
            with tabs[0]:
                df_build = pd.DataFrame(
                    build,
                    columns=["Артефакт", "Тир", "Количество"]
                )
                st.dataframe(df_build, hide_index=True, height=30 + len(df_build) * 35 + 8)

            with tabs[1]:
                txt_pretty = "\n".join(
                    f"{i + 1}. {name} (Тир {tier}) – {cnt} шт." for i, (name, tier, cnt) in enumerate(build)
                )
                st.code(txt_pretty, language="markdown")

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
                            st.dataframe(df_stats, use_container_width=True, hide_index=True)

        if btn_cols[6].button("ℹ️",
                              key="legend_btn",
                              help="Показать или скрыть легенду: что означают свойства в таблице",
                              use_container_width=True):
            st.session_state.show_legend = not st.session_state.get("show_legend", False)
            st.rerun()

        if st.session_state.get("show_legend", False):
            items_html = "".join(
                f"<p style='margin:4px 0;'><strong>{icon}</strong> — {desc}</p>"
                for icon, desc in ALIASES_DESCR_MAP.items()
            )
            html = f"""
            <div style="
                border:1px solid #24272D;
                border-radius:8px;
                padding:12px;
                background-color:#1A1C24;
            ">
              {items_html}              
            </div>
            <br>
            """
            legend_container.markdown(html, unsafe_allow_html=True)
        else:
            legend_container.empty()
