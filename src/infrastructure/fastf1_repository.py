"""
Module: infrastructure/fastf1_repository.py
Responsibility: Single point of access to the FastF1 API.
Implements the Singleton pattern to guarantee one shared cache-enabled
FastF1 instance per process, with thread-safe initialization and
exponential-backoff retry logic for transient network errors.
"""

import logging
import threading
import time
from typing import Optional

import fastf1
import fastf1.core

from src.infrastructure.cache_manager import CacheManager
from src.shared.constants import (
    API_MAX_RETRIES,
    API_RETRY_BACKOFF_BASE,
    DATA_CACHE_DIR,
    DriverCode,
    GrandPrix,
    LapNumber,
    Year,
)

logger = logging.getLogger(__name__)


class FastF1Repository:
    """Thread-safe Singleton repository for FastF1 data access.

    Usage:
        repo = FastF1Repository()           # always returns the same instance
        session = repo.get_session(2023, "Monza", "Q")
        lap = repo.get_lap(session, "VER", 1)

    The FastF1 cache is activated once during the first instantiation and
    pointed at the project-local ``data_cache/`` directory.
    """

    _instance: Optional["FastF1Repository"] = None
    _lock: threading.Lock = threading.Lock()
    _initialized: bool = False

    def __new__(cls) -> "FastF1Repository":
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # Guard against repeated __init__ calls on the singleton
        if self._initialized:
            return

        with self._lock:
            if self._initialized:
                return

            self._cache_manager = CacheManager()
            fastf1.Cache.enable_cache(str(self._cache_manager.cache_dir))
            logger.info(
                "FastF1Repository initialized. Cache: %s",
                self._cache_manager.cache_dir,
            )
            FastF1Repository._initialized = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_session(
        self,
        year: Year,
        gp: GrandPrix,
        session_type: str,
    ) -> fastf1.core.Session:
        """Load and return a fully loaded FastF1 Session.

        Retries up to ``API_MAX_RETRIES`` times with exponential backoff on
        transient errors (network timeouts, rate-limiting).

        Args:
            year: Championship year, e.g. 2023.
            gp: Grand Prix name or round number, e.g. "Monza" or 15.
            session_type: FastF1 session identifier — "R", "Q", "FP1", etc.

        Returns:
            A fully loaded ``fastf1.core.Session`` object.

        Raises:
            RuntimeError: If all retry attempts fail.
        """
        session_key = f"{year}_{gp}_{session_type}"
        cached = self._cache_manager.get_from_session(session_key)
        if cached is not None:
            logger.debug("Session '%s' served from Streamlit session cache.", session_key)
            return cached

        session = self._retry(
            lambda: self._load_session(year, gp, session_type),
            context=f"get_session({year}, {gp}, {session_type})",
        )
        self._cache_manager.set_in_session(session_key, session)
        return session

    def get_fastest_lap(
        self,
        session: fastf1.core.Session,
        driver: DriverCode,
    ) -> fastf1.core.Lap:
        """Retrieve the fastest valid lap for a driver in the session.

        Args:
            session: A loaded FastF1 Session (returned by ``get_session``).
            driver: Three-letter driver code, e.g. "VER".

        Returns:
            The fastest ``fastf1.core.Lap`` for the driver.

        Raises:
            ValueError: If no valid lap is found for the driver.
        """
        lap = session.laps.pick_driver(driver).pick_fastest()
        if lap is None:
            raise ValueError(
                f"No valid fastest lap found for driver '{driver}' "
                f"in session '{session.event['EventName']} {session.name}'."
            )
        return lap

    def get_lap(
        self,
        session: fastf1.core.Session,
        driver: DriverCode,
        lap_number: LapNumber,
    ) -> fastf1.core.Lap:
        """Retrieve a specific lap for a driver within an already-loaded session.

        Args:
            session: A loaded FastF1 Session (returned by ``get_session``).
            driver: Three-letter driver code, e.g. "VER".
            lap_number: 1-based lap number.

        Returns:
            The matching ``fastf1.core.Lap`` object with telemetry attached.

        Raises:
            ValueError: If the driver or lap number is not found in the session.
        """
        laps = session.laps.pick_driver(driver)
        matching = laps[laps["LapNumber"] == lap_number]

        if matching.empty:
            raise ValueError(
                f"Lap {lap_number} for driver '{driver}' not found in session "
                f"'{session.event['EventName']} {session.name}'."
            )

        lap: fastf1.core.Lap = matching.iloc[0]
        return lap

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_session(
        year: Year,
        gp: GrandPrix,
        session_type: str,
    ) -> fastf1.core.Session:
        """Internal: create and load a FastF1 session (no retry logic here)."""
        session = fastf1.get_session(year, gp, session_type)
        session.load()
        return session

    @staticmethod
    def _retry(func, context: str):
        """Execute *func* with exponential backoff on exception.

        Args:
            func: Zero-argument callable to execute.
            context: Human-readable description for log messages.

        Returns:
            The return value of *func*.

        Raises:
            RuntimeError: After all retries are exhausted.
        """
        last_exc: Optional[Exception] = None

        for attempt in range(1, API_MAX_RETRIES + 1):
            try:
                return func()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                wait = API_RETRY_BACKOFF_BASE ** attempt
                logger.warning(
                    "[%s] Attempt %d/%d failed: %s. Retrying in %.1fs…",
                    context,
                    attempt,
                    API_MAX_RETRIES,
                    exc,
                    wait,
                )
                if attempt < API_MAX_RETRIES:
                    time.sleep(wait)

        raise RuntimeError(
            f"[{context}] All {API_MAX_RETRIES} attempts failed. "
            f"Last error: {last_exc}"
        ) from last_exc
