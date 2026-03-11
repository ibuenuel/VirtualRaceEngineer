"""
Module: ui/components.py
Responsibility: Reusable UI component library for the Virtual Race Engineer.
All components render via st.markdown with custom CSS classes defined in
style_utils.py. Components accept plain Python types — no Streamlit state.
"""

from typing import TYPE_CHECKING, Optional

import streamlit as st

if TYPE_CHECKING:
    from src.services.ai_verdict_service import Verdict

from src.domain.models import DriverStats
from src.ui.style_utils import theme


def driver_badge(driver_code: str, slot: str = "a") -> None:
    """Render a coloured pill badge with the driver code.

    Args:
        driver_code: Three-letter driver code, e.g. "VER".
        slot: "a" for Driver A (blue) or "b" for Driver B (orange).
    """
    css_class = f"vre-badge vre-badge-{slot}"
    dot_color = theme()["driver_a"] if slot == "a" else theme()["driver_b"]
    st.markdown(
        f'<span class="{css_class}">'
        f'<span style="width:8px;height:8px;border-radius:50%;'
        f'background:{dot_color};display:inline-block;"></span>'
        f"{driver_code.upper()}</span>",
        unsafe_allow_html=True,
    )


def stat_card(label: str, value: str, delta: Optional[str] = None) -> None:
    """Render a single metric card with an optional delta indicator.

    Args:
        label: Short metric name shown above the value, e.g. "Max Speed".
        value: Formatted metric value, e.g. "342 km/h".
        delta: Optional delta string. Prefix with "+" for positive (green)
               or "-" for negative (red), e.g. "+0.4s" or "-12 km/h".
    """
    delta_html = ""
    if delta:
        if delta.startswith("+"):
            delta_html = f'<div class="vre-delta-pos">{delta}</div>'
        elif delta.startswith("-"):
            delta_html = f'<div class="vre-delta-neg">{delta}</div>'
        else:
            delta_html = f'<div style="color:#8a8a8a">{delta}</div>'

    st.markdown(
        f"""
        <div class="vre-card">
          <div style="font-size:0.75rem;font-weight:600;letter-spacing:0.08em;
                      text-transform:uppercase;color:#8a8a8a;margin-bottom:0.4rem;">
            {label}
          </div>
          <div style="font-size:1.6rem;font-weight:700;line-height:1.1;">
            {value}
          </div>
          {delta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def driver_stats_row(stats_a: DriverStats, stats_b: DriverStats) -> None:
    """Render a side-by-side comparison row for two drivers' key stats.

    Each metric is shown with a delta relative to Driver B (stats_b).

    Args:
        stats_a: Aggregated stats for Driver A.
        stats_b: Aggregated stats for Driver B.
    """
    cols = st.columns(4, gap="small")

    def _fmt(value: Optional[float], unit: str = "", decimals: int = 1) -> str:
        if value is None:
            return "—"
        return f"{value:.{decimals}f}{unit}"

    def _delta(a: Optional[float], b: Optional[float], unit: str = "", higher_is_better: bool = True) -> Optional[str]:
        if a is None or b is None:
            return None
        diff = a - b
        sign = "+" if diff >= 0 else ""
        is_positive = diff >= 0 if higher_is_better else diff <= 0
        prefix = "+" if is_positive else ""
        # Force the sign from actual diff
        return f"{sign}{diff:.1f}{unit}"

    with cols[0]:
        stat_card(
            "Lap Time",
            _fmt(stats_a.lap_time_seconds, "s"),
            _delta(stats_a.lap_time_seconds, stats_b.lap_time_seconds, "s", higher_is_better=False),
        )
    with cols[1]:
        stat_card(
            "Max Speed",
            _fmt(stats_a.max_speed_kph, " km/h", 0),
            _delta(stats_a.max_speed_kph, stats_b.max_speed_kph, " km/h"),
        )
    with cols[2]:
        stat_card(
            "Avg Throttle",
            _fmt(stats_a.avg_throttle_pct, "%", 1),
            _delta(stats_a.avg_throttle_pct, stats_b.avg_throttle_pct, "%"),
        )
    with cols[3]:
        stat_card(
            "Avg Brake",
            _fmt(stats_a.avg_brake_pct, "%", 1),
            _delta(stats_a.avg_brake_pct, stats_b.avg_brake_pct, "%"),
        )


def section_header(title: str, subtitle: Optional[str] = None) -> None:
    """Render a styled section heading with optional subtitle.

    Args:
        title: Main heading text.
        subtitle: Optional secondary description shown below the title.
    """
    sub_html = (
        f'<p style="color:#8a8a8a;font-size:0.9rem;margin-top:0.2rem;">{subtitle}</p>'
        if subtitle
        else ""
    )
    st.markdown(
        f"""
        <div style="margin-bottom:1rem;">
          <h2 style="margin-bottom:0;font-size:1.25rem;font-weight:700;">{title}</h2>
          {sub_html}
        </div>
        <hr class="vre-divider"/>
        """,
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: Optional[str] = None) -> None:
    """Render the top-level page title with F1 red accent bar.

    Args:
        title: Application or page title.
        subtitle: Optional tagline or context description.
    """
    sub_html = (
        f'<p style="color:#8a8a8a;font-size:1rem;margin-top:0.4rem;">{subtitle}</p>'
        if subtitle
        else ""
    )
    st.markdown(
        f"""
        <div style="border-left:4px solid #e8002d;padding-left:1rem;margin-bottom:2rem;">
          <h1 style="margin:0;font-size:2rem;font-weight:800;letter-spacing:-0.03em;">
            {title}
          </h1>
          {sub_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def verdict_card(verdict: "Verdict") -> None:
    """Render the full Race Engineer Verdict with all six sections.

    Displays the headline as a banner, four analysis sections in a 2-column
    grid, and the conclusion as a full-width summary card.

    Args:
        verdict: Populated Verdict dataclass from AIVerdictService.
    """
    from src.ui.style_utils import theme

    t = theme()

    # --- Headline banner ---
    st.markdown(
        f"""
        <div style="border-left:4px solid #e8002d;background:#1e1e1e;
                    border-radius:8px;padding:1.2rem 1.4rem;margin-bottom:1.5rem;">
          <div style="font-size:0.7rem;font-weight:700;letter-spacing:0.12em;
                      text-transform:uppercase;color:#8a8a8a;margin-bottom:0.5rem;">
            Race Engineer Verdict
          </div>
          <div style="font-size:1.15rem;font-weight:700;line-height:1.4;">
            {verdict.headline}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- Four analysis sections in 2 x 2 grid ---
    sections = [
        ("Speed Analysis", verdict.speed_analysis, t["driver_a"]),
        ("Driving Style", verdict.style_analysis, t["driver_b"]),
        ("Micro-Sector Dominance", verdict.dominance_analysis, "#a78bfa"),
        ("Overtake Profile", verdict.overtake_analysis, "#34d399"),
    ]

    col_left, col_right = st.columns(2, gap="medium")
    cols = [col_left, col_right]

    for i, (title, text, accent) in enumerate(sections):
        with cols[i % 2]:
            st.markdown(
                f"""
                <div class="vre-card" style="margin-bottom:1rem;min-height:120px;">
                  <div style="font-size:0.7rem;font-weight:700;letter-spacing:0.1em;
                              text-transform:uppercase;color:{accent};margin-bottom:0.6rem;">
                    {title}
                  </div>
                  <div style="font-size:0.88rem;line-height:1.6;color:#d4d4d4;">
                    {text}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # --- Conclusion (full width) ---
    st.markdown(
        f"""
        <div style="background:#1a1f2e;border:1px solid #2a3250;border-radius:8px;
                    padding:1.2rem 1.4rem;margin-top:0.5rem;">
          <div style="font-size:0.7rem;font-weight:700;letter-spacing:0.1em;
                      text-transform:uppercase;color:#e8002d;margin-bottom:0.6rem;">
            Engineering Conclusion
          </div>
          <div style="font-size:0.95rem;line-height:1.7;color:#e0e0e0;font-weight:500;">
            {verdict.conclusion}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
