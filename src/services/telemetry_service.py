"""
Module: services/telemetry_service.py
Responsibility: Core telemetry processing pipeline.
Converts raw FastF1 lap telemetry into distance-aligned DataFrames so that
two drivers' data points correspond to the same track position rather than
the same timestamp — the prerequisite for every meaningful comparison.

Key concepts:
  - Distance grid: a 1-D array of evenly-spaced track positions (meters).
  - Interpolation: each telemetry channel is re-sampled onto the grid via
    scipy linear interpolation, removing the effect of different car speeds
    on sampling frequency.
  - LapSync: pairs two laps and returns both re-sampled onto an identical grid,
    making column-wise arithmetic (e.g. Speed_A - Speed_B) valid.
"""

import logging
from dataclasses import dataclass

import fastf1.core
import numpy as np
import pandas as pd
from scipy import interpolate

from src.shared.constants import (
    COL_BRAKE,
    COL_DISTANCE,
    COL_DRS,
    COL_GEAR,
    COL_RPM,
    COL_SPEED,
    COL_THROTTLE,
    COL_X,
    COL_Y,
    DriverCode,
)

logger = logging.getLogger(__name__)

# Telemetry channels re-sampled during interpolation
_CHANNELS = [COL_SPEED, COL_THROTTLE, COL_BRAKE, COL_GEAR, COL_RPM, COL_DRS, COL_X, COL_Y]

# Grid resolution in meters — 1 m gives ~5 000 points for a 5 km lap
_GRID_RESOLUTION_M: float = 1.0


@dataclass(frozen=True)
class SyncedLaps:
    """Holds the outputs of a LapSync operation.

    Attributes:
        grid: 1-D array of distance values (meters) shared by both DataFrames.
        telemetry_a: Re-sampled telemetry for Driver A (index = grid).
        telemetry_b: Re-sampled telemetry for Driver B (index = grid).
        driver_a: Three-letter code for Driver A.
        driver_b: Three-letter code for Driver B.
        lap_distance_m: Total lap distance in metres.
    """

    grid: np.ndarray
    telemetry_a: pd.DataFrame
    telemetry_b: pd.DataFrame
    driver_a: DriverCode
    driver_b: DriverCode
    lap_distance_m: float


class TelemetryService:
    """Provides distance-based telemetry alignment for two F1 laps.

    All methods are stateless and can be called without instantiation, but
    a service instance is recommended for dependency injection in tests.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sync_laps(
        self,
        lap_a: fastf1.core.Lap,
        lap_b: fastf1.core.Lap,
        driver_a: DriverCode,
        driver_b: DriverCode,
        grid_resolution_m: float = _GRID_RESOLUTION_M,
    ) -> SyncedLaps:
        """Align two laps onto a common distance grid.

        This is the main entry point for the telemetry engine. Both laps are
        independently interpolated onto the same grid so every row index
        corresponds to the same track position.

        Args:
            lap_a: FastF1 Lap object for Driver A.
            lap_b: FastF1 Lap object for Driver B.
            driver_a: Driver A code for labelling.
            driver_b: Driver B code for labelling.
            grid_resolution_m: Spacing between grid points in metres.

        Returns:
            A SyncedLaps dataclass with aligned DataFrames.

        Raises:
            ValueError: If telemetry cannot be loaded for either lap.
        """
        tel_a = self._load_telemetry(lap_a, driver_a)
        tel_b = self._load_telemetry(lap_b, driver_b)

        # Build a grid spanning the shorter of the two laps to avoid
        # extrapolation at the end of the longer lap.
        max_dist = min(tel_a[COL_DISTANCE].max(), tel_b[COL_DISTANCE].max())
        grid = self._build_grid(max_dist, grid_resolution_m)

        resampled_a = self._interpolate_to_grid(tel_a, grid)
        resampled_b = self._interpolate_to_grid(tel_b, grid)

        logger.info(
            "LapSync complete: %s vs %s | %.0f m | %d grid points",
            driver_a,
            driver_b,
            max_dist,
            len(grid),
        )

        return SyncedLaps(
            grid=grid,
            telemetry_a=resampled_a,
            telemetry_b=resampled_b,
            driver_a=driver_a,
            driver_b=driver_b,
            lap_distance_m=float(max_dist),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_telemetry(lap: fastf1.core.Lap, driver: DriverCode) -> pd.DataFrame:
        """Fetch and validate telemetry for a single lap.

        Args:
            lap: FastF1 Lap row.
            driver: Driver code used in error messages.

        Returns:
            Raw telemetry DataFrame with a clean Distance column.

        Raises:
            ValueError: If telemetry is missing or the Distance column is absent.
        """
        try:
            tel = lap.get_telemetry()
        except Exception as exc:
            raise ValueError(
                f"Could not load telemetry for driver '{driver}': {exc}"
            ) from exc

        if tel is None or tel.empty:
            raise ValueError(f"Empty telemetry for driver '{driver}'.")

        if COL_DISTANCE not in tel.columns:
            raise ValueError(
                f"Telemetry for driver '{driver}' is missing the Distance column."
            )

        # Drop duplicate distance values to avoid interpolation artefacts
        tel = tel.drop_duplicates(subset=[COL_DISTANCE]).sort_values(COL_DISTANCE)
        return tel.reset_index(drop=True)

    @staticmethod
    def _build_grid(max_distance: float, resolution: float) -> np.ndarray:
        """Create a uniformly-spaced distance grid from 0 to max_distance.

        Args:
            max_distance: Upper bound in metres.
            resolution: Step size in metres.

        Returns:
            1-D numpy array of distance values.
        """
        return np.arange(0.0, max_distance, resolution)

    @staticmethod
    def _interpolate_to_grid(telemetry: pd.DataFrame, grid: np.ndarray) -> pd.DataFrame:
        """Re-sample all telemetry channels onto the provided distance grid.

        Uses scipy linear interpolation per channel. Values outside the
        measured distance range are clipped to the boundary values.

        Args:
            telemetry: Raw telemetry DataFrame with a Distance column.
            grid: Target distance array.

        Returns:
            DataFrame indexed by the grid with one column per channel.
        """
        dist = telemetry[COL_DISTANCE].to_numpy(dtype=float)
        result: dict[str, np.ndarray] = {COL_DISTANCE: grid}

        for channel in _CHANNELS:
            if channel not in telemetry.columns:
                # Fill missing channels with NaN rather than crashing
                result[channel] = np.full(len(grid), np.nan)
                continue

            values = telemetry[channel].to_numpy(dtype=float)
            # Remove NaN pairs before interpolating
            valid = ~np.isnan(values)
            if valid.sum() < 2:
                result[channel] = np.full(len(grid), np.nan)
                continue

            interp_fn = interpolate.interp1d(
                dist[valid],
                values[valid],
                kind="linear",
                bounds_error=False,
                fill_value=(values[valid][0], values[valid][-1]),  # clip
            )
            result[channel] = interp_fn(grid)

        return pd.DataFrame(result).set_index(COL_DISTANCE)
