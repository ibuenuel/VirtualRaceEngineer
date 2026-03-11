"""
Module: services/strategies/micro_sector.py
Responsibility: MicroSectorStrategy — divides the lap into fixed 50-metre
segments and determines which driver dominated each one.

"Dominance" is defined as having the lower cumulative time through that
segment (i.e. being faster on average across those 50 metres).

Output:
  - A DataFrame with one row per segment, showing who won it and by how much.
  - A colour-coded dominance map suitable for overlaying on the track X/Y map.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.services.analysis_engine import AnalysisEngine, AnalysisResult
from src.services.telemetry_service import SyncedLaps
from src.shared.constants import COL_SPEED, MICRO_SECTOR_LENGTH_M


@dataclass(frozen=True)
class SectorResult:
    """Result for a single micro-sector.

    Attributes:
        sector_index: 0-based sector number.
        start_m: Distance at sector start (metres).
        end_m: Distance at sector end (metres).
        winner: Driver code of the sector winner.
        margin_s: Time advantage of the winner in seconds.
        delta_s: Signed time delta (negative = Driver A faster).
    """

    sector_index: int
    start_m: float
    end_m: float
    winner: str
    margin_s: float
    delta_s: float


class MicroSectorStrategy(AnalysisEngine):
    """Divides the lap into 50 m segments and assigns a winner to each.

    Uses the SpeedDelta formula per segment:
        Δt_segment = Σ (Δd × (1/v_A − 1/v_B) × (1/3.6))

    A negative segment sum means Driver A was faster in that sector.

    Args:
        segment_length_m: Segment size in metres. Defaults to MICRO_SECTOR_LENGTH_M (50).
    """

    def __init__(self, segment_length_m: int = MICRO_SECTOR_LENGTH_M) -> None:
        self._segment_length = segment_length_m

    @property
    def name(self) -> str:
        return "MicroSector"

    def analyze(self, synced: SyncedLaps) -> AnalysisResult:
        """Compute per-segment dominance for the full lap.

        Args:
            synced: Distance-aligned telemetry from TelemetryService.

        Returns:
            AnalysisResult with a per-segment DataFrame and summary metrics.
        """
        speed_a = synced.telemetry_a[COL_SPEED].to_numpy(dtype=float)
        speed_b = synced.telemetry_b[COL_SPEED].to_numpy(dtype=float)
        grid = synced.grid
        delta_d = grid[1] - grid[0] if len(grid) > 1 else 1.0

        # Per-metre time delta (positive = A loses time)
        speed_a_safe = np.clip(speed_a, 10.0, None)
        speed_b_safe = np.clip(speed_b, 10.0, None)
        time_delta_per_m = delta_d * 3.6 * (1.0 / speed_a_safe - 1.0 / speed_b_safe)

        # Segment boundaries
        step = max(1, int(self._segment_length / delta_d))
        sectors: list[SectorResult] = []
        rows: list[dict] = []

        for i, start_idx in enumerate(range(0, len(grid), step)):
            end_idx = min(start_idx + step, len(grid))
            segment_delta = float(time_delta_per_m[start_idx:end_idx].sum())
            start_m = float(grid[start_idx])
            end_m = float(grid[end_idx - 1])

            winner = synced.driver_a if segment_delta < 0 else synced.driver_b
            margin = abs(segment_delta)

            sector = SectorResult(
                sector_index=i,
                start_m=start_m,
                end_m=end_m,
                winner=winner,
                margin_s=round(margin, 4),
                delta_s=round(segment_delta, 4),
            )
            sectors.append(sector)
            rows.append(
                {
                    "Sector": i + 1,
                    "Start_m": start_m,
                    "End_m": end_m,
                    "Winner": winner,
                    "Margin_s": round(margin, 4),
                    "Delta_s": round(segment_delta, 4),
                    # Normalised dominance score -1…+1 for colour maps
                    "DominanceScore": np.clip(segment_delta / 0.1, -1.0, 1.0),
                }
            )

        df = pd.DataFrame(rows).set_index("Sector")

        summary = self._build_summary(sectors, synced.driver_a, synced.driver_b)

        return AnalysisResult(
            strategy_name=self.name,
            driver_a=synced.driver_a,
            driver_b=synced.driver_b,
            data=df,
            summary=summary,
            metadata={"sectors": [s.__dict__ for s in sectors]},
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_summary(
        sectors: list[SectorResult], driver_a: str, driver_b: str
    ) -> dict:
        total = len(sectors)
        wins_a = sum(1 for s in sectors if s.winner == driver_a)
        wins_b = total - wins_a

        # Biggest single-sector advantage
        best_a = max((s for s in sectors if s.winner == driver_a), key=lambda s: s.margin_s, default=None)
        best_b = max((s for s in sectors if s.winner == driver_b), key=lambda s: s.margin_s, default=None)

        return {
            "total_sectors": total,
            f"sectors_won_{driver_a}": wins_a,
            f"sectors_won_{driver_b}": wins_b,
            "dominant_driver": driver_a if wins_a > wins_b else driver_b,
            "dominance_ratio": round(max(wins_a, wins_b) / total * 100, 1),
            f"best_sector_{driver_a}": best_a.sector_index + 1 if best_a else None,
            f"best_sector_{driver_b}": best_b.sector_index + 1 if best_b else None,
        }
