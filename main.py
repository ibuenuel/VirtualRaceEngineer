"""
Module: main.py
Responsibility: Entry point for the Virtual Race Engineer Streamlit application.

Flow when user clicks Load Session:
  1. FastF1Repository loads the session (cached in st.session_state).
  2. get_fastest_lap() retrieves each driver's best lap.
  3. TelemetryService.sync_laps() aligns both laps onto a 1-m distance grid.
  4. Four AnalysisEngine strategies run in sequence.
  5. AIVerdictService aggregates strategy outputs into a human-readable verdict.
  6. Results are stored in st.session_state so tab-switches do not re-run analysis.
  7. Charts and verdict are rendered across five tab panels.

Run with: streamlit run main.py
"""

import pandas as pd
import streamlit as st

from src.domain.models import DriverStats
from src.infrastructure.fastf1_repository import FastF1Repository
from src.services.ai_verdict_service import AIVerdictService
from src.services.strategies.driver_dna import DriverDNAStrategy
from src.services.strategies.micro_sector import MicroSectorStrategy
from src.services.strategies.overtake_profile import OvertakeProfileStrategy
from src.services.strategies.speed_delta import SpeedDeltaStrategy
from src.services.telemetry_service import TelemetryService
from src.shared.constants import COL_SPEED
from src.ui.charts import (
    delta_chart,
    micro_sector_chart,
    overtake_chart,
    speed_trace_chart,
    throttle_brake_chart,
    track_heatmap,
)
from src.ui.components import (
    driver_badge,
    driver_stats_row,
    page_header,
    section_header,
    verdict_card,
)
from src.ui.style_utils import inject_styles

# Must be the very first Streamlit call
st.set_page_config(
    page_title="Virtual Race Engineer",
    page_icon="🏁",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_styles()

# ---------------------------------------------------------------------------
# Session-state key for caching analysis results across Streamlit re-runs
# ---------------------------------------------------------------------------

_RESULTS_KEY = "vre_analysis_results"

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

    # Show cached state indicator when results are present
    if _RESULTS_KEY in st.session_state:
        cached = st.session_state[_RESULTS_KEY]
        st.markdown(
            f'<div style="font-size:0.75rem;color:#4ade80;margin-top:0.5rem;">'
            f'Loaded: {cached["gp"]} {cached["year"]} — {cached["session_type"]}<br>'
            f'{cached["driver_a"]} vs {cached["driver_b"]}</div>',
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Main area — Page header (always visible)
# ---------------------------------------------------------------------------

page_header(
    "Virtual Race Engineer",
    "F1 Telemetry Analysis Platform",
)

# ---------------------------------------------------------------------------
# Load button handler — run full analysis pipeline
# ---------------------------------------------------------------------------

if load_btn:
    if not gp or not driver_a or not driver_b:
        st.warning("Please fill in Grand Prix, Driver A, and Driver B before loading.")
    else:
        try:
            repo = FastF1Repository()

            with st.spinner(f"Loading {gp} {year} {session_type}…"):
                session = repo.get_session(year, gp, session_type)
                lap_a = repo.get_fastest_lap(session, driver_a)
                lap_b = repo.get_fastest_lap(session, driver_b)

            with st.spinner("Synchronising telemetry…"):
                synced = TelemetryService().sync_laps(lap_a, lap_b, driver_a, driver_b)

            with st.spinner("Running analysis strategies…"):
                speed_result = SpeedDeltaStrategy().analyze(synced)
                dna_result = DriverDNAStrategy().analyze(synced)
                micro_result = MicroSectorStrategy().analyze(synced)
                overtake_result = OvertakeProfileStrategy().analyze(synced)

            verdict = AIVerdictService().generate(
                driver_a=driver_a,
                driver_b=driver_b,
                speed_result=speed_result,
                dna_result=dna_result,
                micro_result=micro_result,
                overtake_result=overtake_result,
            )

            # Build DriverStats from lap metadata + DNA profiles
            def _get(profile, key):
                if profile is None:
                    return None
                return profile[key] if isinstance(profile, dict) else getattr(profile, key)

            dna_summary = dna_result.summary
            profile_a = dna_summary.get("driver_a_profile")
            profile_b = dna_summary.get("driver_b_profile")

            def _lap_time(lap) -> float | None:
                try:
                    lt = lap["LapTime"]
                    return float(lt.total_seconds()) if pd.notna(lt) else None
                except Exception:
                    return None

            stats_a = DriverStats(
                driver=driver_a,
                lap_time_seconds=_lap_time(lap_a),
                max_speed_kph=float(synced.telemetry_a[COL_SPEED].max()),
                avg_speed_kph=float(synced.telemetry_a[COL_SPEED].mean()),
                avg_throttle_pct=_get(profile_a, "avg_throttle_pct"),
                avg_brake_pct=_get(profile_a, "avg_brake_pct"),
                distance_m=synced.lap_distance_m,
            )
            stats_b = DriverStats(
                driver=driver_b,
                lap_time_seconds=_lap_time(lap_b),
                max_speed_kph=float(synced.telemetry_b[COL_SPEED].max()),
                avg_speed_kph=float(synced.telemetry_b[COL_SPEED].mean()),
                avg_throttle_pct=_get(profile_b, "avg_throttle_pct"),
                avg_brake_pct=_get(profile_b, "avg_brake_pct"),
                distance_m=synced.lap_distance_m,
            )

            # Cache everything in session_state
            st.session_state[_RESULTS_KEY] = {
                "synced": synced,
                "speed_result": speed_result,
                "dna_result": dna_result,
                "micro_result": micro_result,
                "overtake_result": overtake_result,
                "verdict": verdict,
                "stats_a": stats_a,
                "stats_b": stats_b,
                "gp": gp,
                "year": year,
                "session_type": session_type,
                "driver_a": driver_a,
                "driver_b": driver_b,
            }
            st.rerun()

        except Exception as exc:  # noqa: BLE001
            st.error(f"Failed to load session: {exc}")

# ---------------------------------------------------------------------------
# Results area — renders whenever cached results are available
# ---------------------------------------------------------------------------

if _RESULTS_KEY in st.session_state:
    r = st.session_state[_RESULTS_KEY]
    synced = r["synced"]
    speed_result = r["speed_result"]
    dna_result = r["dna_result"]
    micro_result = r["micro_result"]
    overtake_result = r["overtake_result"]
    verdict = r["verdict"]
    stats_a = r["stats_a"]
    stats_b = r["stats_b"]

    # --- Session header ---
    section_header(
        f"{r['gp']} {r['year']} — {r['session_type']}",
        f"Fastest lap comparison  ·  {r['driver_a']} vs {r['driver_b']}",
    )

    # --- Driver badges ---
    badge_col_a, badge_col_b, *_ = st.columns([1, 1, 4])
    with badge_col_a:
        driver_badge(r["driver_a"], "a")
    with badge_col_b:
        driver_badge(r["driver_b"], "b")

    st.markdown("<div style='margin:0.8rem 0'/>", unsafe_allow_html=True)

    # --- Key stats row ---
    driver_stats_row(stats_a, stats_b)

    st.markdown("<div style='margin:1.5rem 0'/>", unsafe_allow_html=True)

    # --- Analysis tabs ---
    tabs = st.tabs([
        "Speed Analysis",
        "Driver DNA",
        "Micro-Sector",
        "Overtake Profile",
        "Engineer Verdict",
    ])

    with tabs[0]:
        section_header("Speed Analysis", "Distance-based speed comparison and time delta")
        st.plotly_chart(speed_trace_chart(synced), use_container_width=True)
        st.plotly_chart(delta_chart(speed_result), use_container_width=True)

    with tabs[1]:
        section_header("Driver DNA", "Throttle and brake signature analysis")
        st.plotly_chart(throttle_brake_chart(synced), use_container_width=True)

        # DNA profile table
        dna_summary = dna_result.summary
        profile_a = dna_summary.get("driver_a_profile")
        profile_b = dna_summary.get("driver_b_profile")

        if profile_a is not None and profile_b is not None:
            def _get(p, key):
                return p[key] if isinstance(p, dict) else getattr(p, key)

            dna_data = {
                "Metric": ["Aggressiveness (0–100)", "Smoothness (0–100)", "Brake Profile",
                            "Full Throttle %", "Heavy Braking %"],
                r["driver_a"]: [
                    f"{_get(profile_a, 'aggressiveness'):.0f}",
                    f"{_get(profile_a, 'smoothness'):.0f}",
                    _get(profile_a, "brake_profile"),
                    f"{_get(profile_a, 'full_throttle_pct_of_lap'):.1f}%",
                    f"{_get(profile_a, 'heavy_braking_pct_of_lap'):.1f}%",
                ],
                r["driver_b"]: [
                    f"{_get(profile_b, 'aggressiveness'):.0f}",
                    f"{_get(profile_b, 'smoothness'):.0f}",
                    _get(profile_b, "brake_profile"),
                    f"{_get(profile_b, 'full_throttle_pct_of_lap'):.1f}%",
                    f"{_get(profile_b, 'heavy_braking_pct_of_lap'):.1f}%",
                ],
            }
            st.dataframe(
                pd.DataFrame(dna_data).set_index("Metric"),
                use_container_width=True,
            )

    with tabs[2]:
        section_header("Micro-Sector Dominance", "50 m segment control across the full lap")
        chart_col, map_col = st.columns([3, 2], gap="medium")
        with chart_col:
            st.plotly_chart(micro_sector_chart(micro_result), use_container_width=True)
        with map_col:
            st.plotly_chart(track_heatmap(synced, micro_result), use_container_width=True)

    with tabs[3]:
        section_header("Overtake Profile", "Corner exit speed advantage per zone")
        st.plotly_chart(overtake_chart(overtake_result), use_container_width=True)

        if not overtake_result.data.empty:
            st.dataframe(overtake_result.data, use_container_width=True)

    with tabs[4]:
        section_header("Race Engineer Verdict", "AI-generated performance summary")
        verdict_card(verdict)

elif not load_btn:
    # Onboarding screen — no data loaded yet
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
