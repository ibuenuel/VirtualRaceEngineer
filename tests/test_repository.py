"""
Module: tests/test_repository.py
Responsibility: Unit tests for FastF1Repository and CacheManager.
All FastF1 API calls are mocked to avoid real network access.
Run with: pytest tests/test_repository.py -v
"""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.infrastructure.cache_manager import CacheManager
from src.infrastructure.fastf1_repository import FastF1Repository


# ---------------------------------------------------------------------------
# CacheManager tests
# ---------------------------------------------------------------------------


class TestCacheManager:
    def test_cache_dir_is_created(self, tmp_path: Path) -> None:
        target = tmp_path / "new_cache"
        assert not target.exists()
        cm = CacheManager(cache_dir=target)
        assert target.exists()
        assert cm.cache_dir == target

    def test_valid_entry_within_ttl(self, tmp_path: Path) -> None:
        cm = CacheManager(cache_dir=tmp_path, ttl_seconds=3600)
        entry = tmp_path / "session.pkl"
        entry.write_bytes(b"data")
        assert cm.is_entry_valid(entry) is True

    def test_stale_entry_beyond_ttl(self, tmp_path: Path) -> None:
        cm = CacheManager(cache_dir=tmp_path, ttl_seconds=1)
        entry = tmp_path / "session.pkl"
        entry.write_bytes(b"data")
        # Backdate modification time by 10 seconds
        old_time = time.time() - 10
        import os
        os.utime(entry, (old_time, old_time))
        assert cm.is_entry_valid(entry) is False

    def test_missing_entry_is_invalid(self, tmp_path: Path) -> None:
        cm = CacheManager(cache_dir=tmp_path)
        assert cm.is_entry_valid(tmp_path / "nonexistent.pkl") is False

    def test_invalidate_removes_file(self, tmp_path: Path) -> None:
        cm = CacheManager(cache_dir=tmp_path)
        entry = tmp_path / "session.pkl"
        entry.write_bytes(b"data")
        cm.invalidate(entry)
        assert not entry.exists()

    def test_session_state_fallback_outside_streamlit(self) -> None:
        # Should not raise even without Streamlit context
        CacheManager.set_in_session("key", "value")
        result = CacheManager.get_from_session("key", default="fallback")
        assert result == "fallback"


# ---------------------------------------------------------------------------
# FastF1Repository Singleton tests
# ---------------------------------------------------------------------------


class TestFastF1RepositorySingleton:
    def test_singleton_returns_same_instance(self) -> None:
        repo1 = FastF1Repository()
        repo2 = FastF1Repository()
        assert repo1 is repo2

    def test_singleton_id_consistent(self) -> None:
        assert id(FastF1Repository()) == id(FastF1Repository())


# ---------------------------------------------------------------------------
# FastF1Repository.get_session tests
# ---------------------------------------------------------------------------


class TestGetSession:
    @patch("src.infrastructure.fastf1_repository.fastf1.get_session")
    def test_get_session_loads_and_returns(self, mock_get_session: MagicMock) -> None:
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session

        repo = FastF1Repository()
        # Clear any in-memory session cache to force a fresh load
        with patch.object(repo._cache_manager, "get_from_session", return_value=None):
            with patch.object(repo._cache_manager, "set_in_session"):
                result = repo.get_session(2023, "Monza", "Q")

        mock_session.load.assert_called_once()
        assert result is mock_session

    @patch("src.infrastructure.fastf1_repository.fastf1.get_session")
    def test_get_session_retries_on_failure(self, mock_get_session: MagicMock) -> None:
        mock_session = MagicMock()
        # Fail twice, succeed on third attempt
        mock_get_session.side_effect = [
            ConnectionError("timeout"),
            ConnectionError("timeout"),
            mock_session,
        ]

        repo = FastF1Repository()
        with patch.object(repo._cache_manager, "get_from_session", return_value=None):
            with patch.object(repo._cache_manager, "set_in_session"):
                with patch("src.infrastructure.fastf1_repository.time.sleep"):
                    result = repo.get_session(2023, "Spa", "R")

        assert mock_get_session.call_count == 3
        assert result is mock_session

    @patch("src.infrastructure.fastf1_repository.fastf1.get_session")
    def test_get_session_raises_after_max_retries(self, mock_get_session: MagicMock) -> None:
        mock_get_session.side_effect = ConnectionError("always fails")

        repo = FastF1Repository()
        with patch.object(repo._cache_manager, "get_from_session", return_value=None):
            with patch.object(repo._cache_manager, "set_in_session"):
                with patch("src.infrastructure.fastf1_repository.time.sleep"):
                    with pytest.raises(RuntimeError, match="All 3 attempts failed"):
                        repo.get_session(2023, "Monaco", "Q")


# ---------------------------------------------------------------------------
# FastF1Repository.get_lap tests
# ---------------------------------------------------------------------------


class TestGetLap:
    def _make_session(self, driver: str, lap_number: int) -> MagicMock:
        """Build a minimal mock Session with one lap."""
        lap_data = pd.DataFrame({
            "LapNumber": [lap_number],
            "Driver": [driver],
            "LapTime": [pd.Timedelta("1:18.500")],
        })
        mock_laps = MagicMock()
        mock_laps.pick_driver.return_value = lap_data

        mock_session = MagicMock()
        mock_session.laps = mock_laps
        mock_session.event = {"EventName": "Italian Grand Prix"}
        mock_session.name = "Qualifying"
        return mock_session

    def test_get_lap_returns_correct_row(self) -> None:
        session = self._make_session("VER", 1)
        repo = FastF1Repository()
        lap = repo.get_lap(session, "VER", 1)
        assert lap["LapNumber"] == 1
        assert lap["Driver"] == "VER"

    def test_get_lap_raises_for_missing_lap(self) -> None:
        session = self._make_session("VER", 1)
        repo = FastF1Repository()
        with pytest.raises(ValueError, match="Lap 99"):
            repo.get_lap(session, "VER", 99)
