import json
import time
import base64
import textwrap
import pandas as pd
import streamlit as st
import extra_streamlit_components as stx
from pathlib import Path
from typing import Dict, List
from collections import defaultdict
from pandas.io.formats.style import Styler

from src.utils.constants import (ALIASES,
                                 ALL_STAT_KEYS,
                                 BASE_URL,
                                 DEFAULT_DATA_FILE,
                                 GROUPING_CFG,
                                 STAT_KEYS,
                                 )


def load_artifacts() -> Dict[str, Dict[str, Dict[str, float]]]:
    if not DEFAULT_DATA_FILE.exists():
        st.error(f"Не найден {DEFAULT_DATA_FILE.as_posix()}")
        st.stop()
    return json.loads(Path(DEFAULT_DATA_FILE).read_text(encoding="utf-8"))


def init_session_state_df() -> None:
    ss = st.session_state
    if "build_df" not in ss:
        ss.build_df = pd.DataFrame(columns=["Артефакт", "Тир", "Количество"], dtype=object)

    ss.setdefault("search_q", "")
    ss.setdefault("tier_sel", 3)

    for p in STAT_KEYS:
        ss.setdefault(f"f_{p}", False)


def df_from_encoded_build(encoded: str) -> pd.DataFrame:
    """Переводим base64‑строку из URL/куки в DataFrame."""
    raw = base64.urlsafe_b64decode(encoded.encode()).decode()
    obj = json.loads(raw)
    df = pd.DataFrame(
        obj,
        columns=["name", "tier", "count"],
    ).rename(columns={"name": "Артефакт", "tier": "Тир", "count": "Количество"})
    return df.astype({"Тир": int, "Количество": int})


def encoded_build_from_df(df: pd.DataFrame) -> str:
    """Сериализуем DataFrame в base64‑строку."""
    tup = [
        {"name": n, "tier": int(t), "count": int(c)}
        for n, t, c in df[["Артефакт", "Тир", "Количество"]].to_records(index=False)
    ]
    raw = json.dumps(tup, ensure_ascii=False)
    return base64.urlsafe_b64encode(raw.encode()).decode()


def remove_zero_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Убираем строки, где Количество <= 0."""
    return df[df["Количество"] > 0].reset_index(drop=True)


def add_artifact_to_df(name: str, tier: int, qty: int = 1) -> None:
    """Добаляет/увеличивает позицию в build_df."""
    df = st.session_state.build_df.copy()
    mask = (df["Артефакт"] == name) & (df["Тир"] == tier)

    if mask.any():
        df.loc[mask, "Количество"] += qty
    else:
        df = pd.concat(
            [
                df,
                pd.DataFrame({
                    "Артефакт": [name],
                    "Тир": [tier],
                    "Количество": [qty],
                }),
            ],
            ignore_index=True,
        )

    st.session_state.build_df = remove_zero_rows(df)


def group_by_char_length(items: List[str], max_chars: int = 50, overhead: int = 3):
    rows, cur, cur_len = [], [], 0
    for itm in items:
        ln = len(itm) + overhead
        if cur and cur_len + ln > max_chars:
            rows.append(cur)
            cur, cur_len = [], 0
        cur.append(itm)
        cur_len += ln
    if cur:
        rows.append(cur)
    return rows


def get_artifact_tooltip(art_data, name, tier, aliases):
    props = art_data[name][str(tier)]
    lines = []
    for prop, value in props.items():
        if abs(value) < 1e-6:
            continue
        label = aliases.get(prop, prop)
        lines.append(f"{label}: {value:+.1f}")
    return " | \n".join(lines) or "Нет эффектов"


def render_artifact_buttons_df(art_data: Dict, tier_sel: int, max_chars: int = 50) -> None:
    """Печатаем сетку кнопок. Клик → add_artifact_to_df."""
    ss = st.session_state
    names = sorted(art_data.keys())

    q = ss.search_q.lower()
    if q:
        names = [n for n in names if q in n.lower()]

    active_props = [p for p in STAT_KEYS if ss.get(f"f_{p}")]
    if active_props:
        names = [
            n for n in names
            if any(art_data[n][str(tier_sel)].get(p, 0) > 0 for p in active_props)
        ]

    for row in group_by_char_length(names, max_chars):
        cols = st.columns(len(row), gap="small")
        for col, name in zip(cols, row):
            tooltip = get_artifact_tooltip(art_data, name, tier_sel, ALIASES)
            if col.button(name, key=f"btn_{name}_{tier_sel}", help=tooltip, use_container_width=True):
                add_artifact_to_df(name, tier_sel, 1)
                st.rerun()


def _collapse_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Складываем строки с одинаковыми (Артефакт, Тир)."""
    if df.empty:
        return df

    agg = (
        df.groupby(["Артефакт", "Тир"], as_index=False, sort=False)["Количество"]
        .sum()
    )

    agg = agg[agg["Количество"] > 0]
    return agg.astype({"Тир": int, "Количество": int}).reset_index(drop=True)


def render_build_editor() -> None:
    df_original = st.session_state.build_df

    df_edited = st.data_editor(
        df_original,
        hide_index=True,
        use_container_width=True,
        key="build_df_editor",
        column_config={
            "Артефакт": st.column_config.TextColumn("Артефакт", disabled=True),
            "Тир": st.column_config.NumberColumn("Тир", min_value=1, max_value=4, step=1),
            "Количество": st.column_config.NumberColumn("Количество", min_value=0, max_value=25, step=1),
        },
    )

    if not df_edited.equals(df_original):
        collapsed = _collapse_duplicates(df_edited)
        st.session_state.build_df = _collapse_duplicates(df_edited)
        if len(collapsed) != len(df_edited):
            st.rerun()


def render_build_interactive() -> None:
    """Интерактивная правка build_df кнопками-контролами."""
    df = st.session_state.build_df

    hdr = st.columns([4.4, 1.2, 1.8, 0.5], gap="small")
    hdr[0].markdown("**Артефакт**")
    hdr[1].markdown("**Тир**")
    hdr[2].markdown("**Количество**")

    for idx, row in df.sort_values(["Артефакт", "Тир"]).iterrows():
        cols = st.columns([4, 1.2, 1.8, 0.5], gap="small")

        cols[0].markdown(
            f"<div style='margin-top:5px;font-size:18px;'>"
            f"<strong>{row['Артефакт']}</strong></div>",
            unsafe_allow_html=True,
        )

        new_tier = cols[1].selectbox(
            "Тир", [1, 2, 3, 4],
            index=int(row["Тир"]) - 1,
            key=f"tier_{idx}",
            label_visibility="collapsed",
        )

        new_qty = cols[2].number_input(
            "Количество", 0, 25, int(row["Количество"]),
            step=1,
            key=f"qty_{idx}",
            label_visibility="collapsed",
        )

        if cols[3].button("❌", key=f"del_{idx}"):
            st.session_state.build_df = df.drop(idx).reset_index(drop=True)
            st.rerun()

        if (new_tier != row["Тир"]) or (new_qty != row["Количество"]):
            tmp_df = df.copy()

            dup_mask = (
                    (tmp_df["Артефакт"] == row["Артефакт"])
                    & (tmp_df["Тир"] == new_tier)
                    & (tmp_df.index != idx)
            )
            if dup_mask.any():
                dup_idx = tmp_df[dup_mask].index[0]
                tmp_df.at[dup_idx, "Количество"] += new_qty
                tmp_df = tmp_df.drop(idx)
            else:
                tmp_df.at[idx, "Тир"] = new_tier
                tmp_df.at[idx, "Количество"] = new_qty

            tmp_df = tmp_df[tmp_df["Количество"] > 0].reset_index(drop=True)
            st.session_state.build_df = tmp_df
            st.rerun()


def calc_summary_df(build_df: pd.DataFrame, art_data: Dict[str, Dict[str, Dict[str, float]]]):
    res = defaultdict(float)
    for _, row in build_df.iterrows():
        props = art_data[row["Артефакт"]][str(int(row["Тир"]))]
        qty = int(row["Количество"])
        for prop in ALL_STAT_KEYS:
            res[prop] += props.get(prop, 0.0) * qty
    return res


def assemble_metrics_df(summary: Dict[str, float]) -> pd.DataFrame:
    rows, covered = [], set()

    for key, cfg in GROUPING_CFG.items():
        total = 0.0
        for rule in cfg["group"]:
            col = rule["column"]
            sign = rule.get("sign", 1)
            total += summary.get(col, 0.0) * sign
            covered.add(col)
        rows.append({"Свойство": cfg["name"], "Значение": total})

    for prop, val in summary.items():
        if prop in covered or abs(val) < 1e-6:
            continue
        display_name = ALIASES.get(prop, prop)
        rows.append({"Свойство": display_name, "Значение": val})

    df = pd.DataFrame(rows)
    df = df[~((df["Свойство"].isin(["🔪 Порезы", "🦴 Переломы"])) & (df["Значение"].abs() < 1e-6))]
    return df


def style_metrics_html(df: pd.DataFrame) -> str:
    def color_cell(v):
        try:
            v = float(v)
        except (ValueError, TypeError):
            return ""
        if v > 0:
            return "color: green"
        if v < 0:
            return "color: red"
        return ""

    styler: Styler = (
        df.style
        .hide(axis="index")
        .format({"Значение": "{:+.1f}"})
        .map(color_cell, subset=["Значение"])
    )

    html_table = styler.to_html()
    extra_css = textwrap.dedent("""
        <style>
          table {width:100% !important; border-collapse:separate !important; border-spacing:0 !important; border:1px solid #3D4044 !important; border-radius:12px !important; overflow:hidden !important;}
          th, td {padding:0 6px !important; font-size:20px !important; height:20px !important;}
        </style>
    """)
    return extra_css + html_table


def manual_calculator_page() -> None:
    init_session_state_df()
    art_data = load_artifacts()
    ss = st.session_state
    cookie_manager = stx.CookieManager(key="cookie_mgr")

    if "build" in st.query_params:
        try:
            encoded = st.query_params.pop("build")
            ss.build_df = df_from_encoded_build(encoded)
        except Exception:
            st.error("Не удалось загрузить сборку из ссылки.")
        finally:
            st.query_params.clear()

    with st.expander("📚 Список всех артефактов", False):
        left, right = st.columns([1.1, 5], gap="small")
        with left:
            st.text_input("🔍 **Поиск**", key="search_q")
            if st.toggle("Показать фильтры", value=False):
                for p in STAT_KEYS:
                    display_name = ALIASES.get(p, p)
                    st.checkbox(display_name, key=f"f_{p}")
        with right:
            tabs = st.tabs([f"Тир {i}" for i in range(1, 5)])
            for i, tab in enumerate(tabs, 1):
                with tab:
                    render_artifact_buttons_df(art_data, tier_sel=i, max_chars=65)

    ctrl_col, build_col, metr_col = st.columns([1.4, 3.2, 1.8], gap="large")

    with ctrl_col:
        st.markdown("<h4 style='margin:0 0 0px'>🧩 Пульт сборки</h4>", unsafe_allow_html=True)
        st.markdown("<hr style='margin:0;border:0;border-top:1px solid #3D4044'>", unsafe_allow_html=True)

        art_name = st.selectbox("Артефакт", sorted(art_data), key="simple_art")
        tier = st.selectbox("Тир", [1, 2, 3, 4], key="simple_tier")

        st.markdown("<div style='height:25px'></div>", unsafe_allow_html=True)
        if st.button("➕ Добавить", key="simple_add"):
            add_artifact_to_df(art_name, tier, 1)
            st.rerun()

    with build_col:
        total = int(ss.build_df["Количество"].sum())
        st.markdown(f"<h4 style='margin:0 0 0px;'>🧾 Артефактный регистр открыт: {total}</h4>", unsafe_allow_html=True)
        st.markdown("<hr style='margin:0;border:0;border-top:1px solid #3D4044'>", unsafe_allow_html=True)

        if ss.build_df.empty:
            st.info("Артефакт, мсье? Или два?")
        else:
            tab_table, tab_ctrl = st.tabs(["📋 Таблица", "🔧 Интерактив"])

            with tab_ctrl:
                render_build_interactive()
            with tab_table:
                render_build_editor()

    with metr_col:
        st.markdown("<h4 style='margin:0 0 0px'>🧠 Что мы собрали?</h4>", unsafe_allow_html=True)
        st.markdown("<hr style='margin:0;border:0;border-top:1px solid #3D4044'>", unsafe_allow_html=True)
        if ss.build_df.empty:
            st.info("Ни одного артефакта… Лакей слегка приуныл")
        else:
            st.markdown("<br>", unsafe_allow_html=True)
            summ = calc_summary_df(ss.build_df, art_data)
            df_metrics = assemble_metrics_df(summ)
            st.markdown(style_metrics_html(df_metrics), unsafe_allow_html=True)

    st.markdown("---")

    share_col, save_col, load_col, clear_col = st.columns(4, gap="small")

    if share_col.button("📤 Поделиться"):
        encoded = encoded_build_from_df(ss.build_df)
        full_url = f"{BASE_URL}?build={encoded}"
        st.success("Персональная ссылка от Лакея")
        st.code(full_url, language="markdown", wrap_lines=True)

    if save_col.button("💾 Сохранить"):
        try:
            cookie_manager.delete("artifact_butler_build")
        except KeyError:
            pass
        cookie_manager.set(
            "artifact_butler_build",
            encoded_build_from_df(ss.build_df),
            expires_at=(pd.Timestamp.utcnow() + pd.Timedelta(days=120)).to_pydatetime(),
            path="/",
            secure=False,
            same_site="lax",
        )
        st.toast("Сборка сохранена!", icon="💾")
        time.sleep(1)
        st.rerun()

    if load_col.button("📥 Загрузить"):
        encoded = cookie_manager.get("artifact_butler_build")
        if encoded:
            ss.build_df = df_from_encoded_build(encoded)
            st.toast("Сборка загружена", icon="📥")
            time.sleep(2)
            st.rerun()
        else:
            st.warning("Хранилище пусто. Лакей лишь вежливо покашлял.")

    if clear_col.button("🗑️ Очистить"):
        ss.build_df = pd.DataFrame(columns=["Артефакт", "Тир", "Количество"], dtype=object)
        st.success("Сборка обнулена. И тишина такая… приятная.")
        time.sleep(2)
        st.rerun()
