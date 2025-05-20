import streamlit as st

def int_input(label: str, value: int, *, min_value=0, max_value=100, key=None) -> int:
    return st.number_input(label, value=value, min_value=min_value, max_value=max_value,
                           step=1, key=key)

def float_input(label: str, value: float, *, min_value=0.0, max_value=1.0, key=None) -> float:
    return st.number_input(label, value=value, min_value=min_value, max_value=max_value,
                           step=0.05, key=key)

def text_input(label: str, value: str = "", key=None) -> str:
    return st.text_input(label, value=value, key=key)

def textarea(label: str, value: str = "", key=None) -> str:
    return st.text_area(label, value=value, key=key)
