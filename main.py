"""
Module: main.py
Responsibility: Entry point for the Virtual Race Engineer Streamlit application.
Configures the page, injects the theme, and renders the base layout with
session selector sidebar and main content area.
Run with: streamlit run main.py
"""

import streamlit as st

from src.ui.style_utils import inject_styles
from src.ui.components import page_header, section_header

# Must be the very first Streamlit call
st.set_page_config(
    page_title="Virtual Race Engineer",
    page_icon="🏁",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_styles()

# ---------------------------------------------------------------------------
# Sidebar — Session selector
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        '<div style="font-size:1.1rem;font-weight:800;letter-spacing:-0.02em;'
        'margin-bottom:1.5rem;">🏁 Virtual Race Engineer</div>',
        unsafe_allow_html=True,
    )

    st.markdown("##### Session")
    year = st.selectbox("Year", options=list(range(2026, 2017, -1)), index=0)
    gp = st.text_input("Grand Prix", placeholder="e.g. Monza, Monaco, Spa")
    session_type = st.selectbox(
        "Session",
        options=["Q", "R", "FP1", "FP2", "FP3", "S"],
        format_func=lambda x: {
            "Q": "Qualifying",
            "R": "Race",
            "FP1": "Practice 1",
            "FP2": "Practice 2",
            "FP3": "Practice 3",
            "S": "Sprint",
        }.get(x, x),
    )

    st.markdown("---")
    st.markdown("##### Drivers")
    driver_a = st.text_input("Driver A", placeholder="e.g. VER", max_chars=3).upper()
    driver_b = st.text_input("Driver B", placeholder="e.g. HAM", max_chars=3).upper()

    st.markdown("---")
    load_btn = st.button("Load Session", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

page_header(
    "Virtual Race Engineer",
    "F1 Telemetry Analysis Platform",
)

if not gp or not driver_a or not driver_b:
    st.markdown(
        """
        <div style="text-align:center;padding:4rem 2rem;color:#8a8a8a;">
          <div style="font-size:3rem;margin-bottom:1rem;">🏎</div>
          <div style="font-size:1.1rem;font-weight:600;margin-bottom:0.5rem;">
            Select a session to get started
          </div>
          <div style="font-size:0.9rem;">
            Choose a Grand Prix, session type, and two drivers in the sidebar,
            then click <strong style="color:#f5f5f5;">Load Session</strong>.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
elif load_btn:
    section_header(
        f"{gp} {year} — {session_type}",
        f"{driver_a}  vs  {driver_b}",
    )
    st.info(
        "Telemetry engine (Phase 3) not yet implemented. "
        "Session parameters are ready to pass to FastF1Repository.",
        icon="ℹ️",
    )
    st.json({
        "year": year,
        "grand_prix": gp,
        "session_type": session_type,
        "driver_a": driver_a,
        "driver_b": driver_b,
    })
