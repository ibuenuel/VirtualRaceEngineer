"""
Module: shared/constants.py
Responsibility: Project-wide constants, configuration defaults, and type aliases.
All magic values belong here — never hardcoded in business logic.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Filesystem paths
# ---------------------------------------------------------------------------

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
DATA_CACHE_DIR: Path = PROJECT_ROOT / "data_cache"

# ---------------------------------------------------------------------------
# Cache configuration
# ---------------------------------------------------------------------------

# Maximum age of a cached FastF1 session file in seconds (default: 7 days)
CACHE_TTL_SECONDS: int = 60 * 60 * 24 * 7

# ---------------------------------------------------------------------------
# FastF1 session type aliases
# ---------------------------------------------------------------------------

SESSION_RACE = "R"
SESSION_QUALIFYING = "Q"
SESSION_SPRINT = "S"
SESSION_PRACTICE_1 = "FP1"
SESSION_PRACTICE_2 = "FP2"
SESSION_PRACTICE_3 = "FP3"

# ---------------------------------------------------------------------------
# Telemetry columns used throughout the application
# ---------------------------------------------------------------------------

COL_DISTANCE = "Distance"
COL_SPEED = "Speed"
COL_THROTTLE = "Throttle"
COL_BRAKE = "Brake"
COL_GEAR = "nGear"
COL_RPM = "RPM"
COL_DRS = "DRS"
COL_X = "X"
COL_Y = "Y"

# ---------------------------------------------------------------------------
# Analysis constants
# ---------------------------------------------------------------------------

# Micro-sector segment length in meters (Blueprint §4)
MICRO_SECTOR_LENGTH_M: int = 50

# Retry configuration for FastF1 API calls
API_MAX_RETRIES: int = 3
API_RETRY_BACKOFF_BASE: float = 2.0  # seconds, exponential: base^attempt

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

DriverCode = str   # e.g. "VER", "HAM"
GrandPrix = str    # e.g. "Monza", "Monaco"
Year = int
LapNumber = int
