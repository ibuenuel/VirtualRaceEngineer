"""
Module: services/strategies/speed_delta.py
Responsibility: SpeedDeltaStrategy — calculates the cumulative time delta
between two drivers at every meter of the lap.

Formula:
    At each grid point i with spacing Δd (metres):
        Δt_i = Δd × (1/v_a_i − 1/v_b_i) × (1/3.6)

    Where speeds are in km/h and the factor 1/3.6 converts to m/s.
    A positive Δt means Driver A is losing time relative to Driver B.

The output DataFrame is the primary input for the speed trace charts
and the micro-sector dominance calculation in Phase 4.
"""

import numpy as np
import pandas as pd

from src.services.analysis_engine import AnalysisEngine, AnalysisResult
from src.services.telemetry_service import SyncedLaps
from src.shared.constants import COL_SPEED

# Minimum speed threshold to avoid division-by-zero in pit lanes / SC
_MIN_SPEED_KPH: float = 10.0


class SpeedDeltaStrategy(AnalysisEngine):
    """Computes per-metre and cumulative time delta between two drivers.

    Output DataFrame columns:
        Speed_A         : Driver A speed (km/h)
        Speed_B         : Driver B speed (km/h)
        SpeedDiff       : Speed_A − Speed_B (km/h)
        TimeDelta_m     : Time delta per metre (seconds, positive = A loses time)
        CumulativeDelta : Running sum of TimeDelta_m (seconds)
    """

    @property
    def name(self) -> str:
        return "SpeedDelta"

    def analyze(self, synced: SyncedLaps) -> AnalysisResult:
        """Calculate speed-based time delta along the lap.

        Args:
            synced: Distance-aligned telemetry from TelemetryService.

        Returns:
            AnalysisResult with the delta DataFrame and summary metrics.
        """
        speed_a = synced.telemetry_a[COL_SPEED].to_numpy(dtype=float)
        speed_b = synced.telemetry_b[COL_SPEED].to_numpy(dtype=float)
        grid = synced.grid

        # Grid spacing (uniform → constant Δd)
        delta_d = grid[1] - grid[0] if len(grid) > 1 else 1.0

        # Clip speeds to avoid division by zero
        speed_a_safe = np.clip(speed_a, _MIN_SPEED_KPH, None)
        speed_b_safe = np.clip(speed_b, _MIN_SPEED_KPH, None)

        # Convert km/h → m/s: v_ms = v_kph / 3.6
        # Time to cover Δd: t = Δd / v_ms = Δd * 3.6 / v_kph
        time_a = delta_d * 3.6 / speed_a_safe
        time_b = delta_d * 3.6 / speed_b_safe

        time_delta_per_m = time_a - time_b          # positive: A slower here
        cumulative_delta = np.cumsum(time_delta_per_m)

        df = pd.DataFrame(
            {
                "Speed_A": speed_a,
                "Speed_B": speed_b,
                "SpeedDiff": speed_a - speed_b,
                "TimeDelta_m": time_delta_per_m,
                "CumulativeDelta": cumulative_delta,
            },
            index=grid,
        )
        df.index.name = "Distance"

        summary = self._build_summary(df, synced.driver_a, synced.driver_b)

        return AnalysisResult(
            strategy_name=self.name,
            driver_a=synced.driver_a,
            driver_b=synced.driver_b,
            data=df,
            summary=summary,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_summary(
        df: pd.DataFrame, driver_a: str, driver_b: str
    ) -> dict:
        """Derive scalar KPIs from the delta DataFrame.

        Args:
            df: Output of the main calculation.
            driver_a: Driver A code.
            driver_b: Driver B code.

        Returns:
            Dictionary of scalar metrics for Stat Cards / AI Verdict.
        """
        final_delta = df["CumulativeDelta"].iloc[-1]
        winner = driver_a if final_delta < 0 else driver_b
        margin = abs(final_delta)

        # Find the zone where the biggest time is gained/lost
        # Segment the lap into 10 equal sectors and sum delta per sector
        n = len(df)
        sector_size = max(1, n // 10)
        sector_deltas = [
            df["TimeDelta_m"].iloc[i : i + sector_size].sum()
            for i in range(0, n, sector_size)
        ]
        biggest_gain_sector = int(np.argmin(sector_deltas))   # most negative = A gains most
        biggest_loss_sector = int(np.argmax(sector_deltas))   # most positive = A loses most

        return {
            "final_delta_s": round(final_delta, 3),
            "margin_s": round(margin, 3),
            "faster_driver": winner,
            "max_speed_diff_kph": round(float(df["SpeedDiff"].abs().max()), 1),
            "avg_speed_diff_kph": round(float(df["SpeedDiff"].mean()), 1),
            "biggest_gain_sector": biggest_gain_sector + 1,
            "biggest_loss_sector": biggest_loss_sector + 1,
        }
