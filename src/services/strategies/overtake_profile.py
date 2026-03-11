"""
Module: services/strategies/overtake_profile.py
Responsibility: OvertakeProfileStrategy — identifies corner exit zones and
scores each driver's exit speed performance to produce an "overtake profile":
where they are strongest for an attack, and most vulnerable to being passed.

Methodology:
  1. Detect corner exits: zones where throttle crosses from < 20% to > 80%
     (the "pick-up" point after the apex).
  2. Measure the mean speed gain over the next EXIT_WINDOW_M metres.
  3. Compare the two drivers' exit speed gain at the same track positions.
  4. Classify each exit as Advantage_A, Advantage_B, or Neutral.

An "Overtake Opportunity" for Driver B is a zone where Driver A exits
slower — Driver B could draw closer under braking into the next corner.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.services.analysis_engine import AnalysisEngine, AnalysisResult
from src.services.telemetry_service import SyncedLaps
from src.shared.constants import COL_SPEED, COL_THROTTLE

# Metres over which exit speed gain is averaged after the pick-up point
EXIT_WINDOW_M: int = 75

# Throttle thresholds for detecting corner exit
_THROTTLE_FLOOR = 20.0    # % — below this = mid-corner
_THROTTLE_CEIL = 80.0     # % — above this = full acceleration

# Minimum speed gain to count as a meaningful exit (filters pit-lane etc.)
_MIN_SPEED_GAIN_KPH = 5.0

# Delta threshold (km/h) below which an exit is considered "Neutral"
_NEUTRAL_THRESHOLD_KPH = 3.0


@dataclass(frozen=True)
class ExitZone:
    """A detected corner exit zone.

    Attributes:
        zone_index: 0-based index of this exit zone.
        pick_up_m: Distance at the throttle pick-up point (metres).
        exit_gain_a: Mean speed gain for Driver A over EXIT_WINDOW_M (km/h).
        exit_gain_b: Mean speed gain for Driver B over EXIT_WINDOW_M (km/h).
        delta_kph: exit_gain_A − exit_gain_B (positive = A better exit).
        advantage: "A", "B", or "Neutral".
    """

    zone_index: int
    pick_up_m: float
    exit_gain_a: float
    exit_gain_b: float
    delta_kph: float
    advantage: str


class OvertakeProfileStrategy(AnalysisEngine):
    """Scores corner exit performance to identify overtaking opportunities.

    Args:
        exit_window_m: Distance window after pick-up point to measure (metres).
    """

    def __init__(self, exit_window_m: int = EXIT_WINDOW_M) -> None:
        self._exit_window = exit_window_m

    @property
    def name(self) -> str:
        return "OvertakeProfile"

    def analyze(self, synced: SyncedLaps) -> AnalysisResult:
        """Detect corner exits and compare exit speed performance.

        Args:
            synced: Distance-aligned telemetry from TelemetryService.

        Returns:
            AnalysisResult with per-exit-zone DataFrame and opportunity summary.
        """
        throttle_a = synced.telemetry_a[COL_THROTTLE].to_numpy(dtype=float)
        speed_a = synced.telemetry_a[COL_SPEED].to_numpy(dtype=float)
        speed_b = synced.telemetry_b[COL_SPEED].to_numpy(dtype=float)
        grid = synced.grid

        # Use Driver A's throttle trace to find pick-up points (same track positions)
        pick_up_indices = self._find_pick_up_points(throttle_a)
        window = max(1, int(self._exit_window / (grid[1] - grid[0]) if len(grid) > 1 else self._exit_window))

        zones: list[ExitZone] = []
        rows: list[dict] = []

        for z_idx, pu_idx in enumerate(pick_up_indices):
            end_idx = min(pu_idx + window, len(grid) - 1)
            if end_idx <= pu_idx:
                continue

            gain_a = float(np.mean(speed_a[pu_idx:end_idx]) - speed_a[pu_idx])
            gain_b = float(np.mean(speed_b[pu_idx:end_idx]) - speed_b[pu_idx])

            if gain_a < _MIN_SPEED_GAIN_KPH and gain_b < _MIN_SPEED_GAIN_KPH:
                continue  # Not a real corner exit

            delta = round(gain_a - gain_b, 2)
            if abs(delta) < _NEUTRAL_THRESHOLD_KPH:
                advantage = "Neutral"
            elif delta > 0:
                advantage = synced.driver_a
            else:
                advantage = synced.driver_b

            zone = ExitZone(
                zone_index=z_idx,
                pick_up_m=round(float(grid[pu_idx]), 1),
                exit_gain_a=round(gain_a, 2),
                exit_gain_b=round(gain_b, 2),
                delta_kph=delta,
                advantage=advantage,
            )
            zones.append(zone)
            rows.append(
                {
                    "Zone": z_idx + 1,
                    "PickUp_m": zone.pick_up_m,
                    f"ExitGain_{synced.driver_a}_kph": gain_a,
                    f"ExitGain_{synced.driver_b}_kph": gain_b,
                    "Delta_kph": delta,
                    "Advantage": advantage,
                }
            )

        df = pd.DataFrame(rows).set_index("Zone") if rows else pd.DataFrame()

        summary = self._build_summary(zones, synced.driver_a, synced.driver_b)

        return AnalysisResult(
            strategy_name=self.name,
            driver_a=synced.driver_a,
            driver_b=synced.driver_b,
            data=df,
            summary=summary,
            metadata={"zones": [z.__dict__ for z in zones]},
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_pick_up_points(throttle: np.ndarray) -> list[int]:
        """Detect indices where throttle transitions from floor to ceiling.

        Looks for the first sample in each acceleration zone where throttle
        exceeds _THROTTLE_CEIL after being below _THROTTLE_FLOOR.

        Args:
            throttle: Throttle array (0–100).

        Returns:
            List of grid indices representing pick-up points.
        """
        indices: list[int] = []
        was_low = False

        for i, val in enumerate(throttle):
            if val < _THROTTLE_FLOOR:
                was_low = True
            elif val > _THROTTLE_CEIL and was_low:
                indices.append(i)
                was_low = False

        return indices

    @staticmethod
    def _build_summary(
        zones: list[ExitZone], driver_a: str, driver_b: str
    ) -> dict:
        if not zones:
            return {"total_exit_zones": 0}

        real_zones = [z for z in zones if z.advantage != "Neutral"]
        wins_a = sum(1 for z in real_zones if z.advantage == driver_a)
        wins_b = sum(1 for z in real_zones if z.advantage == driver_b)
        neutral = len(zones) - len(real_zones)

        # Best individual exit zone
        best_a = max(
            (z for z in zones if z.advantage == driver_a),
            key=lambda z: z.delta_kph,
            default=None,
        )
        best_b = max(
            (z for z in zones if z.advantage == driver_b),
            key=lambda z: abs(z.delta_kph),
            default=None,
        )

        return {
            "total_exit_zones": len(zones),
            f"exit_wins_{driver_a}": wins_a,
            f"exit_wins_{driver_b}": wins_b,
            "neutral_zones": neutral,
            "stronger_on_exits": driver_a if wins_a >= wins_b else driver_b,
            f"best_exit_zone_{driver_a}": best_a.zone_index + 1 if best_a else None,
            f"best_exit_zone_{driver_b}": best_b.zone_index + 1 if best_b else None,
            "avg_delta_kph": round(float(np.mean([z.delta_kph for z in zones])), 2),
        }
