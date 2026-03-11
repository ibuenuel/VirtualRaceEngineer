"""
Module: services/strategies/driver_dna.py
Responsibility: DriverDNAStrategy — analyses the throttle and brake
"signature" of each driver to quantify their driving style.

Metrics produced:
  Aggressiveness (0–100):
    Derived from peak brake pressure and the rate of brake application
    (how sharply the driver stamps on the brakes). High = trail-braker /
    late-braker. Low = early, gentle braker.

  Smoothness (0–100):
    Inverse of the coefficient of variation of the throttle trace.
    A driver who modulates throttle constantly scores low; a driver who
    applies full throttle cleanly scores high.

  Brake Profile Classification:
    "Trail Braker"  — brake pressure stays high deep into the corner
                      (slow release gradient).
    "V-Shaper"      — brake pressure drops sharply (steep release gradient).

The output DataFrame aligns all channels on distance so they can be
directly overlaid on a shared Plotly chart.
"""

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter

from src.services.analysis_engine import AnalysisEngine, AnalysisResult
from src.services.telemetry_service import SyncedLaps
from src.shared.constants import COL_BRAKE, COL_THROTTLE

# Savitzky-Golay smoothing window for derivative calculations.
# Must be odd; 11 m at 1 m resolution = 11 points.
_SG_WINDOW = 11
_SG_POLY = 3

BrakeProfile = Literal["Trail Braker", "V-Shaper", "Balanced"]


@dataclass(frozen=True)
class DriverProfile:
    """Computed style profile for a single driver.

    Attributes:
        driver: Three-letter code.
        aggressiveness: 0–100 composite brake aggressiveness score.
        smoothness: 0–100 throttle smoothness score.
        brake_profile: Qualitative brake shape classification.
        avg_throttle_pct: Mean throttle application over the lap.
        avg_brake_pct: Mean brake application over the lap.
        peak_brake_pct: Maximum brake pressure recorded.
        full_throttle_pct_of_lap: Percentage of lap distance at 98 %+ throttle.
        heavy_braking_pct_of_lap: Percentage of lap distance at 80 %+ brake.
    """

    driver: str
    aggressiveness: float
    smoothness: float
    brake_profile: BrakeProfile
    avg_throttle_pct: float
    avg_brake_pct: float
    peak_brake_pct: float
    full_throttle_pct_of_lap: float
    heavy_braking_pct_of_lap: float


class DriverDNAStrategy(AnalysisEngine):
    """Analyses throttle and brake signatures to produce driver style scores.

    Output DataFrame columns (both drivers, aligned on Distance):
        Throttle_A / Throttle_B : raw throttle (0–100)
        Brake_A    / Brake_B    : raw brake (0–100 or boolean × 100)
        ThrottleSmooth_A/B      : Savitzky-Golay smoothed throttle
        BrakeSmooth_A/B         : Savitzky-Golay smoothed brake
    """

    @property
    def name(self) -> str:
        return "DriverDNA"

    def analyze(self, synced: SyncedLaps) -> AnalysisResult:
        """Compute style scores and brake profile for both drivers.

        Args:
            synced: Distance-aligned telemetry from TelemetryService.

        Returns:
            AnalysisResult with per-driver profile data and comparison summary.
        """
        throttle_a = self._extract_channel(synced.telemetry_a, COL_THROTTLE)
        throttle_b = self._extract_channel(synced.telemetry_b, COL_THROTTLE)
        brake_a = self._extract_channel(synced.telemetry_a, COL_BRAKE)
        brake_b = self._extract_channel(synced.telemetry_b, COL_BRAKE)

        # Normalise boolean brake channels (FastF1 sometimes returns 0/1)
        brake_a = self._normalise_brake(brake_a)
        brake_b = self._normalise_brake(brake_b)

        profile_a = self._build_profile(synced.driver_a, throttle_a, brake_a)
        profile_b = self._build_profile(synced.driver_b, throttle_b, brake_b)

        df = pd.DataFrame(
            {
                "Throttle_A": throttle_a,
                "Throttle_B": throttle_b,
                "Brake_A": brake_a,
                "Brake_B": brake_b,
                "ThrottleSmooth_A": self._smooth(throttle_a),
                "ThrottleSmooth_B": self._smooth(throttle_b),
                "BrakeSmooth_A": self._smooth(brake_a),
                "BrakeSmooth_B": self._smooth(brake_b),
            },
            index=synced.grid,
        )
        df.index.name = "Distance"

        summary = {
            "driver_a_profile": profile_a,
            "driver_b_profile": profile_b,
            "aggressiveness_diff": round(profile_a.aggressiveness - profile_b.aggressiveness, 1),
            "smoothness_diff": round(profile_a.smoothness - profile_b.smoothness, 1),
            "more_aggressive": (
                synced.driver_a if profile_a.aggressiveness >= profile_b.aggressiveness
                else synced.driver_b
            ),
            "smoother_driver": (
                synced.driver_a if profile_a.smoothness >= profile_b.smoothness
                else synced.driver_b
            ),
        }

        return AnalysisResult(
            strategy_name=self.name,
            driver_a=synced.driver_a,
            driver_b=synced.driver_b,
            data=df,
            summary=summary,
            metadata={
                "profile_a": profile_a.__dict__,
                "profile_b": profile_b.__dict__,
            },
        )

    # ------------------------------------------------------------------
    # Profile construction
    # ------------------------------------------------------------------

    def _build_profile(
        self, driver: str, throttle: np.ndarray, brake: np.ndarray
    ) -> DriverProfile:
        """Compute all style metrics for one driver.

        Args:
            driver: Driver code.
            throttle: Throttle array (0–100).
            brake: Brake array (0–100).

        Returns:
            Populated DriverProfile.
        """
        aggressiveness = self._aggressiveness_score(brake)
        smoothness = self._smoothness_score(throttle)
        brake_profile = self._classify_brake_profile(brake)

        n = len(throttle)
        full_throttle_pct = float(np.sum(throttle >= 98) / n * 100)
        heavy_braking_pct = float(np.sum(brake >= 80) / n * 100)

        return DriverProfile(
            driver=driver,
            aggressiveness=round(aggressiveness, 1),
            smoothness=round(smoothness, 1),
            brake_profile=brake_profile,
            avg_throttle_pct=round(float(np.nanmean(throttle)), 1),
            avg_brake_pct=round(float(np.nanmean(brake)), 1),
            peak_brake_pct=round(float(np.nanmax(brake)), 1),
            full_throttle_pct_of_lap=round(full_throttle_pct, 1),
            heavy_braking_pct_of_lap=round(heavy_braking_pct, 1),
        )

    # ------------------------------------------------------------------
    # Scoring algorithms
    # ------------------------------------------------------------------

    @staticmethod
    def _aggressiveness_score(brake: np.ndarray) -> float:
        """Composite score (0–100) based on peak pressure and onset rate.

        Components:
          - 50 % weight: normalised peak brake pressure (max / 100)
          - 50 % weight: normalised mean positive brake derivative
            (how fast the driver pushes the pedal)

        Args:
            brake: Brake pressure array (0–100).

        Returns:
            Aggressiveness score between 0 and 100.
        """
        peak_score = float(np.nanmax(brake)) / 100.0

        smooth = savgol_filter(brake, window_length=min(_SG_WINDOW, len(brake) | 1), polyorder=_SG_POLY)
        derivative = np.diff(smooth)
        positive_onset = derivative[derivative > 0]
        if len(positive_onset) == 0:
            onset_score = 0.0
        else:
            # Normalise against a reference of 5 %/m onset rate
            onset_score = min(float(np.mean(positive_onset)) / 5.0, 1.0)

        return (0.5 * peak_score + 0.5 * onset_score) * 100.0

    @staticmethod
    def _smoothness_score(throttle: np.ndarray) -> float:
        """Score (0–100) based on throttle trace consistency.

        Uses the inverse coefficient of variation of the smoothed throttle.
        High variance → low smoothness. The score is mapped so that a
        perfectly constant throttle yields 100.

        Args:
            throttle: Throttle application array (0–100).

        Returns:
            Smoothness score between 0 and 100.
        """
        smooth = savgol_filter(throttle, window_length=min(_SG_WINDOW, len(throttle) | 1), polyorder=_SG_POLY)
        std = float(np.std(smooth))
        mean = float(np.mean(smooth))
        if mean < 1.0:
            return 0.0
        cv = std / mean  # coefficient of variation
        # Map: cv=0 → 100, cv≥1 → 0, linear
        return max(0.0, (1.0 - cv) * 100.0)

    @staticmethod
    def _classify_brake_profile(brake: np.ndarray) -> BrakeProfile:
        """Classify braking style from the release gradient of brake events.

        A braking event is identified as a contiguous zone where brake > 20 %.
        The release phase is the second half of each event. The mean gradient
        of the release determines the profile:
          - Steep (< −1.5 %/m average) → "V-Shaper"
          - Shallow (≥ −1.5 %/m)       → "Trail Braker"

        Args:
            brake: Brake pressure array (0–100).

        Returns:
            BrakeProfile classification string.
        """
        smooth = savgol_filter(brake, window_length=min(_SG_WINDOW, len(brake) | 1), polyorder=_SG_POLY)
        gradients: list[float] = []

        in_event = False
        event_start = 0

        for i, val in enumerate(smooth):
            if not in_event and val > 20:
                in_event = True
                event_start = i
            elif in_event and val <= 20:
                in_event = False
                event = smooth[event_start:i]
                if len(event) < 4:
                    continue
                release = event[len(event) // 2 :]
                grad = float(np.mean(np.diff(release)))
                gradients.append(grad)

        if not gradients:
            return "Balanced"

        mean_grad = float(np.mean(gradients))
        if mean_grad < -1.5:
            return "V-Shaper"
        return "Trail Braker"

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_channel(telemetry: pd.DataFrame, col: str) -> np.ndarray:
        if col not in telemetry.columns:
            return np.zeros(len(telemetry))
        return telemetry[col].to_numpy(dtype=float)

    @staticmethod
    def _normalise_brake(brake: np.ndarray) -> np.ndarray:
        """Convert boolean (0/1) brake channels to 0–100 percentage scale."""
        if brake.max() <= 1.0:
            return brake * 100.0
        return brake

    @staticmethod
    def _smooth(arr: np.ndarray) -> np.ndarray:
        n = len(arr)
        window = min(_SG_WINDOW, n if n % 2 != 0 else n - 1)
        if window < _SG_POLY + 2:
            return arr
        return savgol_filter(arr, window_length=window, polyorder=_SG_POLY)
