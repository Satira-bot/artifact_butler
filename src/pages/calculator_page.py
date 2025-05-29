import json
import time
import base64
import textwrap
import pandas as pd
import streamlit as st
import extra_streamlit_components as stx
from typing import Any
from collections import defaultdict
from typing import Dict, List, Tuple
from pandas.io.formats.style import Styler

from src.utils.constants import ALIASES, DEFAULT_DATA_FILE, STAT_KEYS, GROUPING_CFG, BASE_URL, ALL_STAT_KEYS


@st.cache_data(show_spinner=False)
def load_artifacts() -> Dict[str, Dict[str, Dict[str, float]]]:
    if not DEFAULT_DATA_FILE.exists():
        st.error(f"Не найден {DEFAULT_DATA_FILE.as_posix()}")
        st.stop()
    return json.loads(DEFAULT_DATA_FILE.read_text(encoding="utf-8"))


def init_session_state() -> None:
    ss = st.session_state
    ss.setdefault("manual_build", {})
    ss.setdefault("search_q", "")
    ss.setdefault("tier_sel", 3)
    for p in STAT_KEYS:
        ss.setdefault(f"f_{p}", False)


def group_by_char_length(items: List[str], max_chars: int = 50, overhead: int = 3):
    """
    Разбиваем список строк на несколько строк, чтобы не растягивать grid-кнопки.
    """
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


def get_artifact_tooltip(art_data: Dict[str, Dict[str, Dict[str, float]]],
                         name: str,
                         tier: int,
                         aliases: Dict[str, str]
                         ) -> str:
    """
    Собирает строку-подсказку
    """
    props = art_data[name][str(tier)]
    lines = []
    for prop, value in props.items():
        if abs(value) < 1e-6:
            continue

        label = aliases.get(prop, prop)
        lines.append(f"{label}: {value:+.1f}")
    return " | \n".join(lines) or "Нет эффектов"


def render_artifact_buttons(art_data: Dict, tier_sel: int, max_chars: int = 50) -> None:
    """
    Сетка кнопок артефактов (поиск, фильтр, тир).
    """
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
                key = (name, tier_sel)
                ss.manual_build[key] = ss.manual_build.get(key, 0) + 1
                st.rerun()


def render_manual_build() -> None:
    """
    Таблица «Артефакт / Тир / Кол-во / + / −»
    """
    ss = st.session_state
    build = ss.manual_build

    if not build:
        st.info("Артефакт, мсье? Или два?")
        return

    tab_table, tab_ctrl = st.tabs(["📋 Таблица", "🔧 Интерактив"])

    with tab_ctrl:
        header_crtl = st.columns([4.5, 1, 2, 0.5], gap="small")
        header_crtl[0].markdown("**Артефакт**")
        header_crtl[1].markdown("**Тир**")
        header_crtl[2].markdown("**Количество**")

        for (name, tier), qty in sorted(build.items()):
            cols = st.columns([4, 1, 2, 0.5], gap="small")
            cols[0].markdown(
                f"<div style='margin-top:5px; margin-bottom:0; ; font-size:18px;'><strong>{name}</strong></div>",
                unsafe_allow_html=True)
            new_tier = cols[1].selectbox(
                "Тир", [1, 2, 3, 4],
                index=tier - 1,
                key=f"tier_{name}_{tier}",
                label_visibility="collapsed",
            )
            new_qty = cols[2].number_input(
                "Количество", 0, 25, qty,
                step=1,
                key=f"qty_{name}_{tier}",
                label_visibility="collapsed",
            )

            if cols[3].button("❌", key=f"del_{name}_{tier}"):
                ss.manual_build.pop((name, tier), None)
                st.rerun()

            if (new_tier != tier) or (new_qty != qty):
                old_key, new_key = (name, tier), (name, new_tier)
                ss.manual_build.pop(old_key, None)
                if new_qty:
                    ss.manual_build[new_key] = new_qty
                st.rerun()

        with tab_table:
            data = [
                {"Артефакт": n, "Тир": t, "Количество": q}
                for (n, t), q in sorted(build.items())
            ]
            df = pd.DataFrame(data)

            st.dataframe(df, use_container_width=True, hide_index=True)


def calc_summary(build: Dict[Tuple[str, int], int],
                 art_data: Dict[str, Dict[str, Dict[str, float]]]) -> Dict[str, float]:
    """
    Перебираем все артефакты в сборке и суммируем свойства.
    Возвращаем: {property_name: value}.
    """
    res = defaultdict(float)
    for (name, tier), qty in build.items():
        props = art_data[name][str(tier)]
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
    df = df[~((df["Свойство"].isin(["🔪 Порезы", "🦴 Переломы"])) &
              (df["Значение"].abs() < 1e-6))]

    return df


def style_metrics_html(df: pd.DataFrame) -> str:
    def color_cell(v: Any) -> str:
        """Возвращает CSS-правило для ячейки с числом v."""
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

    extra_css = textwrap.dedent("""\
        <style>
          table {
            width:100% !important;
            border-collapse:separate !important;
            border-spacing:0 !important;
            border:1px solid #3D4044 !important;
            border-radius:12px !important;
            overflow:hidden !important;
          }
          th, td {
            padding:0 6px !important;
            font-size:20px !important;
            height:20px !important;
          }
        </style>
    """)

    return extra_css + html_table


def _serialize_build(build_dict):
    raw_json = json.dumps([
        {"name": n, "tier": t, "count": c}
        for (n, t), c in build_dict.items()
    ], ensure_ascii=False)
    return base64.urlsafe_b64encode(raw_json.encode()).decode()


def _deserialize_build(encoded):
    raw = base64.urlsafe_b64decode(encoded).decode()
    obj = json.loads(raw)
    return {(item["name"], item["tier"]): item["count"] for item in obj}


def manual_calculator_page() -> None:
    init_session_state()
    art_data = load_artifacts()
    ss = st.session_state
    cookie_manager = stx.CookieManager(key="cookie_mgr")

    params = st.query_params
    if "build" in params:
        try:
            encoded = params["build"]
            decoded = base64.urlsafe_b64decode(encoded.encode("utf-8"))
            build_list = json.loads(decoded)
            ss = st.session_state
            ss.manual_build = {
                (item["name"], item["tier"]): item["count"]
                for item in build_list
            }
        except Exception:
            st.error("Не удалось загрузить сборку из ссылки.")

    params.pop("build", None)
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
                    render_artifact_buttons(art_data, tier_sel=i, max_chars=65)

    ctrl_col, build_col, metr_col = st.columns([1.3, 3.2, 1.8], gap="large")

    with ctrl_col:
        st.markdown("<h4 style='margin:0 0 0px'>🧩 Пульт сборки</h4>", unsafe_allow_html=True)
        st.markdown(
            """
            <div style='margin:0;padding:0;line-height:0'>
                <hr style='margin:0;border:0;border-top:1px solid #3D4044'>
            </div>
            """,
            unsafe_allow_html=True
        )

        art_name = st.selectbox("Артефакт", sorted(art_data), key="simple_art")
        tier = st.selectbox("Тир", [1, 2, 3, 4], key="simple_tier")

        st.markdown("<div style='height:25px'></div>", unsafe_allow_html=True)
        if st.button("➕ Добавить", key="simple_add"):
            key = (art_name, tier)
            ss.manual_build[key] = ss.manual_build.get(key, 0) + 1
            st.rerun()

    with build_col:
        total = sum(st.session_state.manual_build.values())
        st.markdown(f"<h4 style='margin:0 0 0px;'>🧾 Артефактный регистр открыт: {total}", unsafe_allow_html=True)
        st.markdown(
            """
            <div style='margin:0;padding:0;line-height:0'>
                <hr style='margin:0;border:0;border-top:1px solid #3D4044'>
            </div>
            """,
            unsafe_allow_html=True
        )

        render_manual_build()

    with metr_col:
        st.markdown("<h4 style='margin:0 0 0px'>🧠 Что мы собрали?", unsafe_allow_html=True)
        st.markdown(
            """
            <div style='margin:0;padding:0;line-height:0'>
                <hr style='margin:0;border:0;border-top:1px solid #3D4044'>
            </div>
            """,
            unsafe_allow_html=True
        )
        if not ss.manual_build:
            st.info("Ни одного артефакта… Лакей слегка приуныл")
        else:
            st.markdown("<br>", unsafe_allow_html=True)
            summ = calc_summary(ss.manual_build, art_data)
            df = assemble_metrics_df(summ)
            html = style_metrics_html(df)
            st.markdown(html, unsafe_allow_html=True)

    st.markdown("---")

    share_col, save_col, load_col, clear_col = st.columns(4, gap="small")

    if share_col.button("📤 Поделиться"):
        build_list = [
            {"name": name, "tier": tier, "count": cnt}
            for (name, tier), cnt in st.session_state.manual_build.items()
        ]
        raw = json.dumps(build_list, ensure_ascii=False)
        encoded = base64.urlsafe_b64encode(raw.encode()).decode()

        full_url = f"{BASE_URL}?build={encoded}"

        st.success("Персональная ссылка от Лакея")
        st.code(full_url, language="markdown")

    if save_col.button("💾 Сохранить"):
        try:
            if cookie_manager.get("artifact_butler_build"):
                cookie_manager.delete("artifact_butler_build")
        except KeyError:
            pass

        cookie_manager.set(
            "artifact_butler_build",
            _serialize_build(ss.manual_build),
            expires_at=(pd.Timestamp.utcnow()
                        + pd.Timedelta(days=120)).to_pydatetime(),
            path="/",
            secure=False,
            same_site="lax"
        )
        st.toast("Сборка сохранена!", icon="💾")
        time.sleep(1)
        st.rerun()

    if load_col.button("📥 Загрузить"):
        encoded = cookie_manager.get("artifact_butler_build")
        if encoded:
            ss.manual_build = _deserialize_build(encoded)
            st.toast("Сборка загружена", icon="📥")
            time.sleep(2)
            st.rerun()
        else:
            st.warning("Хранилище пусто. Лакей лишь вежливо покашлял.")

    if clear_col.button("🗑️ Очистить"):
        st.session_state.manual_build.clear()
        st.success("Сборка обнулена. И тишина такая… приятная.")
        time.sleep(2)
        st.rerun()
