"""
Module: main.py
Responsibility: Entry point for the Virtual Race Engineer Streamlit application.
Run with: streamlit run main.py
"""

import streamlit as st

st.set_page_config(
    page_title="Virtual Race Engineer",
    page_icon="🏎️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Virtual Race Engineer")
st.caption("F1 Telemetry Analysis Platform — Phase 1 Infrastructure Ready")

st.info(
    "Infrastructure layer initialized. "
    "UI and telemetry analysis features will be added in upcoming phases.",
    icon="ℹ️",
)
