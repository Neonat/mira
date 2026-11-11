"""Shared visual treatment for the signed-in research console."""
import streamlit as st


def apply_console_style() -> None:
    st.markdown("""<style>
    .stApp { background: #f8f7f3; color: #172b3c; }
    [data-testid="stSidebar"] { background: #edf1ef; border-right: 1px solid #d5dfdc; }
    [data-testid="stMainBlockContainer"] { max-width: 1240px; padding-top: 2rem; }
    h1, h2, h3 { color: #18344b; letter-spacing: -0.02em; }
    [data-testid="stMetric"] { background: #fff; border: 1px solid #dae3df;
      border-radius: 8px; padding: 1rem; font-variant-numeric: tabular-nums; }
    div.stButton > button[kind="primary"], div.stFormSubmitButton > button[kind="primary"] {
      background: #176b68; border-color: #176b68; color: white; }
    :focus-visible { outline: 3px solid #278b83 !important; outline-offset: 2px; }
    </style>""", unsafe_allow_html=True)
