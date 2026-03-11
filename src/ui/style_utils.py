"""
Module: ui/style_utils.py
Responsibility: Injects Tailwind CSS (Play CDN) and custom theme overrides
into the Streamlit application head. Call inject_styles() once at app startup
in main.py before any other st.* calls.
"""

import streamlit as st

# ---------------------------------------------------------------------------
# Colour palette — F1-inspired dark theme
# ---------------------------------------------------------------------------

_THEME = {
    "bg_primary": "#0f0f0f",       # Near-black page background
    "bg_surface": "#1a1a1a",       # Card / surface background
    "bg_elevated": "#242424",      # Elevated elements (hover, active)
    "border": "#2e2e2e",           # Subtle borders
    "text_primary": "#f5f5f5",     # Main text
    "text_muted": "#8a8a8a",       # Secondary / label text
    "accent_red": "#e8002d",       # F1 red
    "accent_white": "#ffffff",
    "driver_a": "#3b82f6",         # Blue — Driver A highlight
    "driver_b": "#f97316",         # Orange — Driver B highlight
    "success": "#22c55e",
    "warning": "#eab308",
}

# ---------------------------------------------------------------------------
# CSS injection
# ---------------------------------------------------------------------------

_TAILWIND_CDN = (
    '<script src="https://cdn.tailwindcss.com"></script>'
)

_CUSTOM_CSS = f"""
<style>
  /* ── Streamlit chrome overrides ── */
  [data-testid="stAppViewContainer"] {{
    background-color: {_THEME['bg_primary']};
  }}
  [data-testid="stSidebar"] {{
    background-color: {_THEME['bg_surface']};
    border-right: 1px solid {_THEME['border']};
  }}
  [data-testid="stHeader"] {{
    background-color: transparent;
  }}
  /* ── Typography ── */
  html, body, [class*="css"] {{
    color: {_THEME['text_primary']};
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
  }}
  h1, h2, h3 {{
    color: {_THEME['text_primary']} !important;
    letter-spacing: -0.02em;
  }}
  /* ── Stat card base ── */
  .vre-card {{
    background: {_THEME['bg_surface']};
    border: 1px solid {_THEME['border']};
    border-radius: 12px;
    padding: 1.25rem 1.5rem;
    transition: border-color 0.2s ease;
  }}
  .vre-card:hover {{
    border-color: {_THEME['accent_red']};
  }}
  /* ── Driver badges ── */
  .vre-badge {{
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.35rem 0.85rem;
    border-radius: 999px;
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }}
  .vre-badge-a {{
    background: {_THEME['driver_a']}22;
    color: {_THEME['driver_a']};
    border: 1px solid {_THEME['driver_a']}55;
  }}
  .vre-badge-b {{
    background: {_THEME['driver_b']}22;
    color: {_THEME['driver_b']};
    border: 1px solid {_THEME['driver_b']}55;
  }}
  /* ── Delta indicators ── */
  .vre-delta-pos {{ color: {_THEME['success']}; font-weight: 600; }}
  .vre-delta-neg {{ color: {_THEME['accent_red']}; font-weight: 600; }}
  /* ── Section divider ── */
  .vre-divider {{
    border: none;
    border-top: 1px solid {_THEME['border']};
    margin: 1.5rem 0;
  }}
  /* ── Streamlit metric overrides ── */
  [data-testid="metric-container"] {{
    background: {_THEME['bg_surface']};
    border: 1px solid {_THEME['border']};
    border-radius: 10px;
    padding: 1rem;
  }}
  /* ── Scrollbar ── */
  ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
  ::-webkit-scrollbar-track {{ background: {_THEME['bg_primary']}; }}
  ::-webkit-scrollbar-thumb {{ background: {_THEME['border']}; border-radius: 3px; }}
</style>
"""


def inject_styles() -> None:
    """Inject Tailwind CDN and custom VRE theme CSS into the Streamlit head.

    Must be called once at the top of main.py, before any other UI rendering.
    """
    st.markdown(_TAILWIND_CDN, unsafe_allow_html=True)
    st.markdown(_CUSTOM_CSS, unsafe_allow_html=True)


def theme() -> dict[str, str]:
    """Return the active colour palette for use in Plotly figures and components.

    Returns:
        Dictionary mapping semantic colour names to hex values.
    """
    return _THEME.copy()
