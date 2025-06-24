import json
import time
import base64
import textwrap
import pandas as pd
import streamlit as st
import extra_streamlit_components as stx
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict

from src.utils.helpers import calculate_table_height
from src.utils.constants import (ALIASES,
                                 ALL_STAT_KEYS,
                                 BASE_URL,
                                 DEFAULT_DATA_FILE,
                                 GROUPING_CFG,
                                 STAT_KEYS,
                                 ALIASES_DESCR
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
        height=calculate_table_height(df_original),
        column_config={
            "Артефакт": st.column_config.TextColumn("Артефакт", disabled=True),
            "Тир": st.column_config.NumberColumn("Тир", min_value=1, max_value=4, step=1),
            "Количество": st.column_config.NumberColumn("Количество", min_value=0, max_value=25, step=1),
        },
    )

    if not df_edited.equals(df_original):
        st.session_state.build_df = _collapse_duplicates(df_edited)
        st.rerun()


def render_build_interactive() -> None:
    """Интерактивная правка build_df кнопками-контролами."""
    df = st.session_state.build_df

    hdr = st.columns([4.4, 1.2, 1.9, 0.5], gap="small")
    hdr[1].markdown("<div style='font-size:16px; margin-bottom: 7px;'>Тир</div>", unsafe_allow_html=True)
    hdr[2].markdown("<div style='font-size:16px; margin-bottom: 7px;'>Количество</div>", unsafe_allow_html=True)

    for idx, row in df.iterrows():
        cols = st.columns([4, 1.2, 1.9, 0.5], gap="small")

        cols[0].markdown(
            f"<div style='margin-top:5px;font-size:17px;'>"
            f"{row['Артефакт']}</div>",
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


def assemble_metrics_df(summary: dict[str, float],
                        build_df: pd.DataFrame,
                        art_data: dict[str, dict[str, dict[str, float]]]
                        ) -> pd.DataFrame:
    """
    Собирает итоговую таблицу метрик
    """
    rows: list[dict[str, Any]] = []
    covered: set[str] = set()

    for key, cfg in GROUPING_CFG.items():
        total = sum(
            summary.get(rule["column"], 0.0) * rule["sign"]
            for rule in cfg["group"]
        )
        name = cfg["name"]
        covered |= {rule["column"] for rule in cfg["group"]}
        rows.append({"Свойство": name, "Значение": total})

    had_change: dict[str, bool] = {}
    for prop in summary:
        if prop in covered:
            continue
        had_change[prop] = any(
            art_data[row["Артефакт"]]
            .get(str(int(row["Тир"])), {})
            .get(prop, 0.0) * int(row["Количество"]) != 0
            for _, row in build_df.iterrows()
        )

    group_had_change: dict[str, bool] = {}
    for key, cfg in GROUPING_CFG.items():
        name = cfg["name"]
        group_had_change[name] = any(
            art_data[row["Артефакт"]]
            .get(str(int(row["Тир"])), {})
            .get(rule["column"], 0.0) * int(row["Количество"]) * rule["sign"] != 0
            for _, row in build_df.iterrows()
            for rule in cfg["group"]
        )

    for prop, val in summary.items():
        if prop in covered:
            continue
        if abs(val) > 1e-6 or had_change.get(prop, False):
            display_name = ALIASES.get(prop, prop)
            rows.append({"Свойство": display_name, "Значение": val})

    df = pd.DataFrame(rows)

    def keep_row(row):
        name, val = row["Свойство"], row["Значение"]

        if abs(val) > 1e-6:
            return True

        if name in group_had_change and group_had_change[name]:
            return True

        atomic_key = next((k for k, v in ALIASES.items() if v == name), name)
        if atomic_key in had_change and had_change[atomic_key]:
            return True
        return False

    return df[df.apply(keep_row, axis=1)]


def style_metrics_html(df: pd.DataFrame) -> str:
    """
    Генерит HTML таблицу
    """
    rows = []
    for _, row in df.iterrows():
        prop = row["Свойство"]
        raw_val = row["Значение"]
        val_str = f"{raw_val:+.1f}"
        desc = ALIASES_DESCR.get(prop, "")

        if prop == "🌡️ Температура":
            color = "inherit"
        else:
            color = "#4CAF50" if raw_val > 0 else ("#E74C3C" if raw_val < 0 else "inherit")

        rows.append(
            f'<tr>'
            f'<td class="has-tooltip" data-tooltip="{desc}">{prop}</td>'
            f'<td style="color: {color};">{val_str}</td>'
            f'</tr>'
        )

    rows_html = "".join(rows)

    html = textwrap.dedent(f"""\
        <table class="custom-metrics">
          <thead>
            <tr><th>Свойство</th><th>Значение</th></tr>
          </thead>
          <tbody>
            {rows_html}
          </tbody>
        </table>
    """)
    return html


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

    ctrl_col, build_col, metr_col = st.columns([1.48, 3.1, 1.9], gap="large")

    with ctrl_col:
        st.markdown("""
        <h4 style="margin:0 0 0px; font-size: 1.3em;"> 🧩 Пульт сборки </h4>
        """, unsafe_allow_html=True)

        st.markdown("<hr style='margin:0;border:0;border-top:1px solid #3D4044'>", unsafe_allow_html=True)

        show_tt = st.toggle("Свойства артефакта", value=False, key="show_tooltips_ctrl")
        art_name = st.selectbox("Артефакт", sorted(art_data), key="simple_art")
        tier = st.selectbox("Тир", [1, 2, 3, 4], key="simple_tier")

        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("➕ Добавить", key="simple_add"):
            current = st.session_state.build_df.loc[
                (st.session_state.build_df["Артефакт"] == art_name) &
                (st.session_state.build_df["Тир"] == tier),
                "Количество"
            ].sum()
            if current < 25:
                add_artifact_to_df(art_name, tier, 1)
            else:
                pass
            st.rerun()

        if show_tt:
            tooltip = get_artifact_tooltip(
                art_data,
                st.session_state.simple_art,
                st.session_state.simple_tier,
                ALIASES
            )
            items = []
            for line in tooltip.split("|"):
                prop, val = line.split(":")
                val = val.strip()
                prop = prop.strip()

                color = "inherit"
                negative_props = {"☢️ Накопление рад.", "🔪 Шанс пореза", "🦴 Шанс перелома"}

                if "Температура" not in prop:
                    num = float(val)
                    if prop in negative_props:
                        if num < 0:
                            color = "#4CAF50"
                        elif num > 0:
                            color = "#E74C3C"
                    else:
                        if num > 0:
                            color = "#4CAF50"
                        elif num < 0:
                            color = "#E74C3C"

                items.append(
                    f"<li>"
                    f"{prop}: "
                    f"<span style='color:{color};'>{val}</span>"
                    f"</li>"
                )

            items_html = "<ul>" + "".join(items) + "</ul>"

            st.markdown(f"""
                <div class="tooltip-container">
                  <strong>{art_name} (Тир {tier}) даёт:</strong>
                  <div class="custom-tooltip">
                    {items_html}
                  </div>
                </div>
                """, unsafe_allow_html=True)

    with build_col:
        total = int(ss.build_df["Количество"].sum())
        st.markdown(f"""
        <h4 style='margin:0 0 0px; font-size: 1.3em;'>🧾 Артефактный регистр открыт: {total} </h4>
        """, unsafe_allow_html=True)

        st.markdown("<hr style='margin:0;border:0;border-top:1px solid #3D4044'>", unsafe_allow_html=True)

        if ss.build_df.empty:
            st.info("""
            📍 В «Пульте сборки» всё просто: выбрал артефакт — добавил.

            🎯 Но если ты хочешь выбрать по фильтрам, свойствам или просто полистать — загляни чуть выше, в блок «📚 Список всех артефактов».

            📦 Когда артефакты уже в сборке — управляй ими здесь, во вкладках:

            - 📋 **Таблица** — редактируй прямо в строках  
            - 🔧 **Интерактив** — кнопочки, выпадающие списки и немного магии  
            - 📝 **Текст** — для копирования, если нужно поделиться или сохранить

            💡 А если сборка пуста — самое время начать.
            """)
        else:
            tab_table, tab_ctrl, tab_text = st.tabs(["📋 Таблица", "🔧 Интерактив", "📝 Текст"])

            with tab_ctrl:
                render_build_interactive()
            with tab_table:
                render_build_editor()
            with tab_text:
                txt = "\n".join(
                    f"{i + 1}. {row['Артефакт']} (Тир {row['Тир']}) – {row['Количество']} шт."
                    for i, row in ss.build_df.iterrows()
                )
                st.code(txt, language="markdown")

    with metr_col:
        st.markdown("""
        <h4 style="margin:0 0 0px; font-size: 1.3em;"> 🧠 Что мы собрали? </h4>
        """, unsafe_allow_html=True)

        st.markdown("<hr style='margin:0;border:0;border-top:1px solid #3D4044'>", unsafe_allow_html=True)
        if ss.build_df.empty:
            st.info("Ни одного артефакта… Лакей слегка приуныл")
        else:
            st.markdown("<br>", unsafe_allow_html=True)
            summ = calc_summary_df(ss.build_df, art_data)
            df_metrics = assemble_metrics_df(summ, ss.build_df, art_data)
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
