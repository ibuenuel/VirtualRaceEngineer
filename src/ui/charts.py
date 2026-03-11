"""
Module: ui/charts.py
Responsibility: Plotly chart builders for the Virtual Race Engineer.

All functions return ``plotly.graph_objects.Figure`` objects.
Rendering (``st.plotly_chart``) is left to the caller so that charts
remain testable and decoupled from Streamlit.

Charts available:
  - speed_trace_chart     : Dual-driver speed overlay vs distance
  - delta_chart           : Cumulative time delta with coloured fill
  - throttle_brake_chart  : 3-row Speed / Throttle / Brake subplot
  - micro_sector_chart    : Per-segment dominance score bar chart
  - track_heatmap         : XY track map coloured by dominance score
  - overtake_chart        : Per-exit-zone delta bar chart
"""

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.services.analysis_engine import AnalysisResult
from src.services.telemetry_service import SyncedLaps
from src.shared.constants import COL_BRAKE, COL_SPEED, COL_THROTTLE, COL_X, COL_Y
from src.ui.style_utils import theme

# ---------------------------------------------------------------------------
# Shared layout defaults — dark F1 theme, transparent paper background
# ---------------------------------------------------------------------------

_LAYOUT_DEFAULTS: dict = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="#1a1a1a",
    font=dict(color="#f5f5f5", family="Inter, sans-serif", size=12),
    margin=dict(l=52, r=24, t=48, b=44),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1.0,
        bgcolor="rgba(0,0,0,0)",
        borderwidth=0,
    ),
    xaxis=dict(gridcolor="#2a2a2a", linecolor="#3a3a3a", zerolinecolor="#3a3a3a"),
    yaxis=dict(gridcolor="#2a2a2a", linecolor="#3a3a3a", zerolinecolor="#3a3a3a"),
)


def _apply_axis_style(fig: go.Figure, rows: int = 1) -> None:
    """Apply dark grid/line colours to all axes in the figure."""
    for i in range(1, rows + 1):
        fig.update_xaxes(gridcolor="#2a2a2a", linecolor="#3a3a3a", row=i, col=1)
        fig.update_yaxes(gridcolor="#2a2a2a", linecolor="#3a3a3a", row=i, col=1)


# ---------------------------------------------------------------------------
# Speed Trace
# ---------------------------------------------------------------------------


def speed_trace_chart(synced: SyncedLaps) -> go.Figure:
    """Dual-driver speed overlay chart.

    Args:
        synced: Distance-aligned telemetry from TelemetryService.

    Returns:
        Plotly Figure with two speed traces.
    """
    t = theme()
    dist = synced.grid
    speed_a = synced.telemetry_a[COL_SPEED].to_numpy()
    speed_b = synced.telemetry_b[COL_SPEED].to_numpy()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dist, y=speed_a,
        name=synced.driver_a,
        line=dict(color=t["driver_a"], width=1.5),
    ))
    fig.add_trace(go.Scatter(
        x=dist, y=speed_b,
        name=synced.driver_b,
        line=dict(color=t["driver_b"], width=1.5),
    ))
    fig.update_layout(
        title="Speed Trace",
        xaxis_title="Distance (m)",
        yaxis_title="Speed (km/h)",
        **_LAYOUT_DEFAULTS,
    )
    return fig


# ---------------------------------------------------------------------------
# Cumulative Time Delta
# ---------------------------------------------------------------------------


def delta_chart(speed_result: AnalysisResult) -> go.Figure:
    """Cumulative time delta chart with split fill areas.

    Negative delta = Driver A faster; positive = Driver B faster.

    Args:
        speed_result: Output of SpeedDeltaStrategy.

    Returns:
        Plotly Figure with delta trace and shaded fill areas.
    """
    t = theme()
    df = speed_result.data
    dist = df.index.to_numpy()
    delta = df["CumulativeDelta"].to_numpy()

    fig = go.Figure()

    # Fill: Driver A faster (delta < 0)
    fig.add_trace(go.Scatter(
        x=dist, y=np.minimum(delta, 0.0),
        fill="tozeroy",
        fillcolor=f"rgba(59,130,246,0.18)",
        line=dict(color="rgba(0,0,0,0)", width=0),
        showlegend=False,
        hoverinfo="skip",
    ))
    # Fill: Driver B faster (delta > 0)
    fig.add_trace(go.Scatter(
        x=dist, y=np.maximum(delta, 0.0),
        fill="tozeroy",
        fillcolor=f"rgba(249,115,22,0.18)",
        line=dict(color="rgba(0,0,0,0)", width=0),
        showlegend=False,
        hoverinfo="skip",
    ))
    # Main delta line
    fig.add_trace(go.Scatter(
        x=dist, y=delta,
        name="Cumulative Δt",
        line=dict(color="#e0e0e0", width=1.8),
        hovertemplate="%{x:.0f} m — Δt: %{y:.3f} s<extra></extra>",
    ))
    # Zero reference line
    fig.add_hline(y=0, line_dash="dash", line_color="#4a4a4a", line_width=1)

    # Driver A badge annotation (left)
    fig.add_annotation(
        x=0.01, y=0.05, xref="paper", yref="paper",
        text=f"◀ {speed_result.driver_a} faster",
        font=dict(color=t["driver_a"], size=11),
        showarrow=False,
    )
    fig.add_annotation(
        x=0.01, y=0.95, xref="paper", yref="paper",
        text=f"◀ {speed_result.driver_b} faster",
        font=dict(color=t["driver_b"], size=11),
        showarrow=False,
    )

    fig.update_layout(
        title="Cumulative Time Delta",
        xaxis_title="Distance (m)",
        yaxis_title="Δt (s)",
        **_LAYOUT_DEFAULTS,
    )
    return fig


# ---------------------------------------------------------------------------
# Throttle / Brake Overlay (3 subplots)
# ---------------------------------------------------------------------------


def throttle_brake_chart(synced: SyncedLaps) -> go.Figure:
    """Three-row subplot: Speed, Throttle, and Brake overlaid for both drivers.

    Args:
        synced: Distance-aligned telemetry from TelemetryService.

    Returns:
        Plotly Figure with 3 vertically stacked subplots sharing x-axis.
    """
    t = theme()
    dist = synced.grid

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.07,
        subplot_titles=(
            f"Speed (km/h)",
            f"Throttle (%)",
            f"Brake (%)",
        ),
    )

    channels = [COL_SPEED, COL_THROTTLE, COL_BRAKE]
    drivers = [
        (synced.driver_a, synced.telemetry_a, t["driver_a"]),
        (synced.driver_b, synced.telemetry_b, t["driver_b"]),
    ]

    for row, channel in enumerate(channels, start=1):
        for driver, tel, color in drivers:
            values = tel[channel].to_numpy(dtype=float)
            fig.add_trace(
                go.Scatter(
                    x=dist,
                    y=values,
                    name=driver,
                    legendgroup=driver,
                    showlegend=(row == 1),
                    line=dict(color=color, width=1.3),
                    hovertemplate=f"{driver} | %{{x:.0f}} m: %{{y:.1f}}<extra></extra>",
                ),
                row=row,
                col=1,
            )

    fig.update_xaxes(title_text="Distance (m)", row=3, col=1)
    fig.update_layout(
        height=580,
        **_LAYOUT_DEFAULTS,
    )
    _apply_axis_style(fig, rows=3)
    return fig


# ---------------------------------------------------------------------------
# Micro-Sector Dominance Bar
# ---------------------------------------------------------------------------


def micro_sector_chart(micro_result: AnalysisResult) -> go.Figure:
    """Per-segment dominance score bar chart.

    Bars above zero = Driver A dominant; below zero = Driver B dominant.

    Args:
        micro_result: Output of MicroSectorStrategy.

    Returns:
        Plotly Figure with one bar per micro-sector.
    """
    t = theme()
    df = micro_result.data

    colors = [
        t["driver_a"] if w == micro_result.driver_a else t["driver_b"]
        for w in df["Winner"]
    ]

    fig = go.Figure(go.Bar(
        x=df.index.tolist(),
        y=df["DominanceScore"].to_numpy(),
        marker_color=colors,
        name="Dominance Score",
        hovertemplate="Sector %{x}<br>Score: %{y:.2f}<extra></extra>",
    ))

    fig.add_hline(y=0, line_color="#4a4a4a", line_width=1)

    # Invisible legend entries to label the colours
    fig.add_trace(go.Bar(
        x=[None], y=[None],
        marker_color=t["driver_a"],
        name=micro_result.driver_a,
        showlegend=True,
    ))
    fig.add_trace(go.Bar(
        x=[None], y=[None],
        marker_color=t["driver_b"],
        name=micro_result.driver_b,
        showlegend=True,
    ))

    fig.update_layout(
        title=f"Micro-Sector Dominance — {micro_result.driver_a} ▲ / {micro_result.driver_b} ▼",
        xaxis_title="Micro-Sector #",
        yaxis_title="Dominance Score (normalised)",
        showlegend=True,
        barmode="overlay",
        **_LAYOUT_DEFAULTS,
    )
    return fig


# ---------------------------------------------------------------------------
# Track Heatmap
# ---------------------------------------------------------------------------


def track_heatmap(synced: SyncedLaps, micro_result: AnalysisResult) -> go.Figure:
    """Track XY map coloured by micro-sector dominance score.

    Uses Driver A's X/Y coordinates and assigns each track position
    the dominance score of its corresponding micro-sector.

    Args:
        synced: Distance-aligned telemetry (must include X and Y channels).
        micro_result: Output of MicroSectorStrategy.

    Returns:
        Plotly Figure with a colour-coded scatter track map, or a
        placeholder figure if XY data is unavailable.
    """
    t = theme()
    x = synced.telemetry_a[COL_X].to_numpy(dtype=float)
    y = synced.telemetry_a[COL_Y].to_numpy(dtype=float)
    grid = synced.grid

    # Guard: no position data available
    valid_mask = ~(np.isnan(x) | np.isnan(y))
    if valid_mask.sum() < 10:
        fig = go.Figure()
        fig.add_annotation(
            text="Track position data unavailable for this session.",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(color="#8a8a8a", size=14),
        )
        fig.update_layout(title="Track Dominance Map", **_LAYOUT_DEFAULTS)
        return fig

    # Map each grid point to a micro-sector dominance score
    df_sectors = micro_result.data.reset_index()  # columns: Sector, Start_m, ...
    boundaries = df_sectors["Start_m"].to_numpy()
    scores_per_sector = df_sectors["DominanceScore"].to_numpy()

    sector_idx = np.digitize(grid, boundaries) - 1
    sector_idx = np.clip(sector_idx, 0, len(scores_per_sector) - 1)
    point_scores = scores_per_sector[sector_idx]

    # Apply mask to all arrays
    x_v = x[valid_mask]
    y_v = y[valid_mask]
    s_v = point_scores[valid_mask]

    fig = go.Figure(go.Scatter(
        x=x_v,
        y=y_v,
        mode="markers",
        marker=dict(
            color=s_v,
            colorscale=[
                [0.0, t["driver_b"]],
                [0.5, "#333333"],
                [1.0, t["driver_a"]],
            ],
            size=3,
            showscale=True,
            colorbar=dict(
                title=dict(text=f"{synced.driver_a} ← → {synced.driver_b}", side="right"),
                tickvals=[-1.0, 0.0, 1.0],
                ticktext=[synced.driver_b, "Even", synced.driver_a],
                thickness=14,
                len=0.7,
            ),
            cmin=-1.0,
            cmax=1.0,
        ),
        hovertemplate="X: %{x:.0f}  Y: %{y:.0f}<br>Score: %{marker.color:.2f}<extra></extra>",
    ))

    fig.update_layout(
        title="Track Dominance Map",
        xaxis=dict(visible=False, scaleanchor="y", scaleratio=1),
        yaxis=dict(visible=False),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#1a1a1a",
        font=dict(color="#f5f5f5", family="Inter, sans-serif", size=12),
        margin=dict(l=16, r=16, t=48, b=16),
    )
    return fig


# ---------------------------------------------------------------------------
# Overtake Profile
# ---------------------------------------------------------------------------


def overtake_chart(overtake_result: AnalysisResult) -> go.Figure:
    """Per-exit-zone delta bar chart.

    Positive bars = Driver A better exit; negative = Driver B better exit;
    near-zero = Neutral.

    Args:
        overtake_result: Output of OvertakeProfileStrategy.

    Returns:
        Plotly Figure with one bar per exit zone.
    """
    t = theme()
    df = overtake_result.data

    if df.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="No corner exit zones detected for this lap.",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(color="#8a8a8a", size=14),
        )
        fig.update_layout(title="Overtake Profile", **_LAYOUT_DEFAULTS)
        return fig

    colors = [
        t["driver_a"] if adv == overtake_result.driver_a
        else (t["driver_b"] if adv == overtake_result.driver_b else "#4a4a4a")
        for adv in df["Advantage"]
    ]

    fig = go.Figure(go.Bar(
        x=df.index.tolist(),
        y=df["Delta_kph"].to_numpy(),
        marker_color=colors,
        name="Exit Delta",
        hovertemplate=(
            "Zone %{x}<br>"
            "Δ Exit Speed: %{y:.1f} km/h<extra></extra>"
        ),
    ))

    fig.add_hline(y=0, line_color="#4a4a4a", line_width=1)

    # Legend colour entries
    fig.add_trace(go.Bar(x=[None], y=[None], marker_color=t["driver_a"],
                         name=overtake_result.driver_a, showlegend=True))
    fig.add_trace(go.Bar(x=[None], y=[None], marker_color=t["driver_b"],
                         name=overtake_result.driver_b, showlegend=True))
    fig.add_trace(go.Bar(x=[None], y=[None], marker_color="#4a4a4a",
                         name="Neutral", showlegend=True))

    fig.update_layout(
        title=(
            f"Corner Exit Advantage — "
            f"{overtake_result.driver_a} (▲) vs {overtake_result.driver_b} (▼)"
        ),
        xaxis_title="Exit Zone #",
        yaxis_title="Δ Exit Speed (km/h)",
        showlegend=True,
        **_LAYOUT_DEFAULTS,
    )
    return fig
