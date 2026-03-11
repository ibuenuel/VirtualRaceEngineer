"""
Module: domain/models.py
Responsibility: Pydantic boundary models for the Virtual Race Engineer domain.
These models validate data at system boundaries (API responses, user input).
Internal telemetry processing uses pandas DataFrames for performance.
"""

from datetime import timedelta
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from src.shared.constants import DriverCode, GrandPrix, LapNumber, Year


class LapModel(BaseModel):
    """Represents the metadata of a single F1 lap.

    Used to validate and transport lap identifiers between layers.
    Does not contain raw telemetry — that lives in a DataFrame.

    Attributes:
        year: Championship year.
        grand_prix: Name of the Grand Prix event.
        session_type: FastF1 session identifier (e.g. "Q", "R").
        driver: Three-letter driver code.
        lap_number: 1-based lap number within the session.
        lap_time: Lap duration. None if the lap was not completed.
        is_personal_best: Whether this was the driver's fastest lap in session.
        compound: Tyre compound, e.g. "SOFT", "MEDIUM", "HARD".
    """

    year: Year = Field(..., ge=1950, le=2100)
    grand_prix: GrandPrix
    session_type: str = Field(..., min_length=1, max_length=4)
    driver: DriverCode = Field(..., min_length=2, max_length=3)
    lap_number: LapNumber = Field(..., ge=1)
    lap_time: Optional[timedelta] = None
    is_personal_best: bool = False
    compound: Optional[str] = None

    @field_validator("driver")
    @classmethod
    def driver_must_be_uppercase(cls, v: str) -> str:
        """Normalise driver codes to uppercase (e.g. 'ver' → 'VER')."""
        return v.upper()

    @field_validator("session_type")
    @classmethod
    def session_type_must_be_uppercase(cls, v: str) -> str:
        return v.upper()

    @property
    def lap_time_seconds(self) -> Optional[float]:
        """Return lap time as total seconds, or None if unavailable."""
        if self.lap_time is None:
            return None
        return self.lap_time.total_seconds()

    model_config = {"frozen": True}  # Immutable value object


class DriverStats(BaseModel):
    """Aggregated performance statistics for a driver in a single lap context.

    Populated by the AnalysisEngine after telemetry processing.

    Attributes:
        driver: Three-letter driver code.
        lap_time_seconds: Total lap time in seconds.
        max_speed_kph: Maximum speed recorded during the lap.
        avg_speed_kph: Mean speed over the entire lap distance.
        avg_throttle_pct: Mean throttle application (0–100).
        avg_brake_pct: Mean brake application (0–100).
        top_gear: Highest gear used during the lap.
        distance_m: Total distance covered in metres.
    """

    driver: DriverCode
    lap_time_seconds: Optional[float] = None
    max_speed_kph: Optional[float] = Field(default=None, ge=0)
    avg_speed_kph: Optional[float] = Field(default=None, ge=0)
    avg_throttle_pct: Optional[float] = Field(default=None, ge=0, le=100)
    avg_brake_pct: Optional[float] = Field(default=None, ge=0, le=100)
    top_gear: Optional[int] = Field(default=None, ge=1, le=9)
    distance_m: Optional[float] = Field(default=None, ge=0)

    @field_validator("driver")
    @classmethod
    def driver_must_be_uppercase(cls, v: str) -> str:
        return v.upper()

    model_config = {"frozen": True}
