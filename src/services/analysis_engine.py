"""
Module: services/analysis_engine.py
Responsibility: Abstract base class for all telemetry analysis strategies.
Defines the contract every concrete strategy must implement and provides
a shared result type. The Strategy Pattern used here allows the AI Verdict
Service to swap between heuristic and LLM-based engines without
changing the calling code.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from src.services.telemetry_service import SyncedLaps


@dataclass
class AnalysisResult:
    """Standardised output for any AnalysisEngine strategy.

    Attributes:
        strategy_name: Human-readable name of the strategy that produced
            this result, e.g. "SpeedDelta" or "DriverDNA".
        driver_a: Three-letter code for Driver A.
        driver_b: Three-letter code for Driver B.
        data: The primary computed DataFrame (content varies by strategy).
        summary: Key scalar metrics for display in Stat Cards.
        metadata: Optional dict for strategy-specific extra data.
    """

    strategy_name: str
    driver_a: str
    driver_b: str
    data: pd.DataFrame
    summary: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class AnalysisEngine(ABC):
    """Abstract base class for telemetry analysis strategies.

    Every strategy receives a SyncedLaps object (the distance-aligned
    telemetry produced by TelemetryService) and returns an AnalysisResult.

    To add a new strategy:
      1. Subclass AnalysisEngine.
      2. Implement ``analyze()``.
      3. Register it in the strategy registry (future: Phase 4 factory).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this strategy, e.g. 'SpeedDelta'."""

    @abstractmethod
    def analyze(self, synced: SyncedLaps) -> AnalysisResult:
        """Run the analysis on distance-aligned lap data.

        Args:
            synced: Output of TelemetryService.sync_laps().

        Returns:
            An AnalysisResult with computed data and summary metrics.
        """
