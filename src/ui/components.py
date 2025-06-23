import streamlit as st

from src.utils.helpers import get_base64_image


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
