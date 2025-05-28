import math
import numpy as np
import pandas as pd
import streamlit as st

from src.utils.helpers import Props, get_base64_image
from src.utils.constants import build_label_alt, build_label_det


def draw_centered_slider_row(df_result: pd.DataFrame,
                             prop_list: list[str],
                             filter_vals: dict[str, float],
                             props: Props,
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


def display_results(best: dict, alts: list[dict], props: Props) -> None:
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

    with st.expander("🔍 Параметры фильтрации", expanded=True):
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


def render_header() -> None:
    bg_img = get_base64_image("assets/bg.jpg")
    bubl_img = get_base64_image("assets/bubl.png")
    flame_img = get_base64_image("assets/flame.png")
    crys_img = get_base64_image("assets/crys.png")
    jelly_img = get_base64_image("assets/jelly.png")

    st.markdown(
        f"""<div class="custom-header" style="
            background-image: url('data:image/png;base64,{bg_img}');
            background-size: cover;
            background-position: center;
            padding: 32px;
            border-radius: 12px;
            margin-bottom: 24px;
        ">
    <div class="header-content">
      <div class="left-spacer"></div>
      <div class="title-block">
        <h1>Артефактный Лакей</h1>
        <p>Ваш проводник в хаосе. Оптимизируем сборки — выживаем красиво</p>
      </div>
      <div class="artifact-row">
        <div class="pulse-green artifact-icon"><img src="data:image/png;base64,{bubl_img}"/></div>
        <div class="pulse-yellow artifact-icon"><img src="data:image/png;base64,{flame_img}"/></div>
        <div class="pulse-red artifact-icon"><img src="data:image/png;base64,{crys_img}"/></div>
        <div class="pulse-brown artifact-icon"><img src="data:image/png;base64,{jelly_img}"/></div>
      </div>
    </div>
    </div>""",
        unsafe_allow_html=True,
    )
