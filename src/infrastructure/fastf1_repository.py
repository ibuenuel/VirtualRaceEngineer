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

# Maps FastF1 session names (from event schedule) to session type codes
_SESSION_NAME_TO_CODE: dict[str, str] = {
    "Practice 1": "FP1",
    "Practice 2": "FP2",
    "Practice 3": "FP3",
    "Qualifying": "Q",
    "Race": "R",
    "Sprint": "S",
    "Sprint Qualifying": "SQ",
    "Sprint Shootout": "SS",
}


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

    def get_event_schedule(self, year: Year) -> list[str]:
        """Return a list of Grand Prix event names for the given season.

        Results are cached in Streamlit session_state so repeated year
        selections do not trigger additional network requests.

        Args:
            year: Championship year, e.g. 2024.

        Returns:
            Sorted list of event name strings, e.g. ``["Bahrain Grand Prix", …]``.
            Returns an empty list if the schedule cannot be fetched.
        """
        cache_key = f"_schedule_{year}"
        cached = self._cache_manager.get_from_session(cache_key)
        if cached is not None:
            return cached

        try:
            schedule = fastf1.get_event_schedule(year, include_testing=False)
            event_names: list[str] = schedule["EventName"].tolist()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not fetch event schedule for %d: %s", year, exc)
            event_names = []

        self._cache_manager.set_in_session(cache_key, event_names)
        return event_names

    def get_event_session_types(self, year: Year, gp: GrandPrix) -> list[str]:
        """Return the session type codes available for a specific Grand Prix.

        Parses the FastF1 event to determine which sessions actually exist
        (e.g. not all rounds have a Sprint). Results are cached in session_state.

        Args:
            year: Championship year.
            gp: Grand Prix event name.

        Returns:
            Ordered list of session type codes, e.g. ``["FP1", "FP2", "FP3", "Q", "R"]``.
            Falls back to the standard five-session weekend if the event cannot be fetched.
        """
        cache_key = f"_session_types_{year}_{gp}"
        cached = self._cache_manager.get_from_session(cache_key)
        if cached is not None:
            return cached

        try:
            event = fastf1.get_event(year, gp)
            session_types: list[str] = []
            for i in range(1, 6):
                name = event.get(f"Session{i}", "")
                if name and str(name).lower() not in ("", "none", "nan"):
                    code = _SESSION_NAME_TO_CODE.get(str(name))
                    if code:
                        session_types.append(code)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not fetch session types for %s %d: %s", gp, year, exc)
            session_types = ["FP1", "FP2", "FP3", "Q", "R"]

        self._cache_manager.set_in_session(cache_key, session_types)
        return session_types

    def get_session_drivers(
        self,
        year: Year,
        gp: GrandPrix,
        session_type: str,
    ) -> dict[str, str]:
        """Return a mapping of driver code → full name for a session.

        Only lap data is fetched — no telemetry — so this is significantly
        faster than ``get_session()``. Results are cached in session_state.

        Args:
            year: Championship year.
            gp: Grand Prix event name.
            session_type: Session identifier, e.g. ``"Q"``.

        Returns:
            Dict sorted by driver code, e.g. ``{"HAM": "Lewis Hamilton", …}``.
            Returns an empty dict if the session has no data yet.
        """
        cache_key = f"_drivers_{year}_{gp}_{session_type}"
        cached = self._cache_manager.get_from_session(cache_key)
        if cached is not None:
            return cached

        try:
            session = self._retry(
                lambda: self._load_session_laps_only(year, gp, session_type),
                context=f"get_session_drivers({year}, {gp}, {session_type})",
                no_retry_on=("does not exist",),
            )
            codes: list[str] = sorted(session.laps["Driver"].unique().tolist())
            drivers: dict[str, str] = {}
            for code in codes:
                try:
                    info = session.get_driver(code)
                    full_name: str = (
                        info.get("FullName")
                        or f"{info.get('FirstName', '')} {info.get('LastName', '')}".strip()
                        or code
                    )
                except Exception:  # noqa: BLE001
                    full_name = code
                drivers[code] = full_name
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not load driver list for %s %d %s: %s", gp, year, session_type, exc)
            drivers = {}

        self._cache_manager.set_in_session(cache_key, drivers)
        return drivers

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
            no_retry_on=("does not exist",),
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
        lap = session.laps.pick_drivers(driver).pick_fastest()
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
        laps = session.laps.pick_drivers(driver)
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
        """Internal: create and fully load a FastF1 session (no retry logic here)."""
        session = fastf1.get_session(year, gp, session_type)
        session.load()
        return session

    @staticmethod
    def _load_session_laps_only(
        year: Year,
        gp: GrandPrix,
        session_type: str,
    ) -> fastf1.core.Session:
        """Internal: load a session with lap data only — no telemetry or weather.

        Significantly faster than ``_load_session``; used to retrieve driver
        lists without waiting for full telemetry download.
        """
        session = fastf1.get_session(year, gp, session_type)
        session.load(laps=True, telemetry=False, weather=False, messages=False)
        return session

    @staticmethod
    def _retry(
        func,
        context: str,
        no_retry_on: tuple[str, ...] = (),
    ):
        """Execute *func* with exponential backoff on exception.

        Args:
            func: Zero-argument callable to execute.
            context: Human-readable description for log messages.
            no_retry_on: Tuple of substrings; if any appears in the exception
                message the error is re-raised immediately without retrying.
                Use this for non-transient errors such as "does not exist".

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
                exc_msg = str(exc).lower()
                if any(pattern.lower() in exc_msg for pattern in no_retry_on):
                    raise
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
