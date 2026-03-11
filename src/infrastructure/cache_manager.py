"""
Module: infrastructure/cache_manager.py
Responsibility: Manages the local filesystem cache for FastF1 session data and
provides a thin wrapper around Streamlit session_state for in-memory caching.
Ensures the cache directory exists and validates entry freshness via TTL.
"""

import time
from pathlib import Path
from typing import Any

from src.shared.constants import DATA_CACHE_DIR, CACHE_TTL_SECONDS


class CacheManager:
    """Handles filesystem cache validation and Streamlit in-memory session state.

    This class is intentionally kept stateless (all methods are pure functions
    operating on the filesystem or injected state) so it can be used safely
    in a Singleton context without locking concerns.

    Args:
        cache_dir: Override for the default cache directory. Useful in tests.
        ttl_seconds: Maximum age (in seconds) before a cache entry is stale.
    """

    def __init__(
        self,
        cache_dir: Path = DATA_CACHE_DIR,
        ttl_seconds: int = CACHE_TTL_SECONDS,
    ) -> None:
        self._cache_dir = cache_dir
        self._ttl_seconds = ttl_seconds
        self._ensure_cache_dir()

    # ------------------------------------------------------------------
    # Filesystem cache
    # ------------------------------------------------------------------

    def _ensure_cache_dir(self) -> None:
        """Create the cache directory if it does not exist."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def cache_dir(self) -> Path:
        """Return the resolved cache directory path."""
        return self._cache_dir

    def is_entry_valid(self, entry_path: Path) -> bool:
        """Check whether a cache entry exists and is within the TTL.

        Args:
            entry_path: Absolute path to the cached file or directory.

        Returns:
            True if the entry exists and its modification time is within
            the configured TTL, False otherwise.
        """
        if not entry_path.exists():
            return False

        age_seconds = time.time() - entry_path.stat().st_mtime
        return age_seconds < self._ttl_seconds

    def invalidate(self, entry_path: Path) -> None:
        """Remove a specific cache entry from the filesystem.

        Args:
            entry_path: Path to the file to remove. Silently ignored if the
                file does not exist.
        """
        if entry_path.is_file():
            entry_path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Streamlit session_state in-memory cache
    # ------------------------------------------------------------------

    @staticmethod
    def get_from_session(key: str, default: Any = None) -> Any:
        """Retrieve a value from Streamlit session_state.

        Falls back gracefully when running outside of a Streamlit context
        (e.g., during unit tests).

        Args:
            key: The session state key.
            default: Value to return if the key is missing.

        Returns:
            The stored value or *default*.
        """
        try:
            import streamlit as st  # noqa: PLC0415 — lazy import intentional

            return st.session_state.get(key, default)
        except Exception:  # noqa: BLE001
            return default

    @staticmethod
    def set_in_session(key: str, value: Any) -> None:
        """Store a value in Streamlit session_state.

        Silently no-ops when running outside of a Streamlit context.

        Args:
            key: The session state key.
            value: The value to store.
        """
        try:
            import streamlit as st  # noqa: PLC0415 — lazy import intentional

            st.session_state[key] = value
        except Exception:  # noqa: BLE001
            pass
