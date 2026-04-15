"""Tests for stockpulse.data.cache module.

Note: Uses pickle intentionally to match the cache module's serialization
format (pickle is the existing contract in stockpulse.data.cache).
"""
import pickle
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

# We patch _CACHE_DIR before importing the module functions so that every test
# operates on an isolated temp directory and never touches real cache files.
_TMP = tempfile.mkdtemp()
_TEST_CACHE_DIR = Path(_TMP) / "test_cache"

# Default config stub used throughout tests.
_TEST_CONFIG = {"cache_ttl_minutes": 15}


def _patch_cache_dir():
    return patch("stockpulse.data.cache._CACHE_DIR", _TEST_CACHE_DIR)


def _patch_config(cfg=None):
    return patch("stockpulse.data.cache.get_config", return_value=cfg or _TEST_CONFIG)


# ---------------------------------------------------------------------------
# set_cached + get_cached round-trip
# ---------------------------------------------------------------------------

def test_round_trip_string():
    with _patch_cache_dir(), _patch_config():
        from stockpulse.data.cache import set_cached, get_cached
        set_cached("test_key_str", "hello world")
        assert get_cached("test_key_str") == "hello world"


def test_round_trip_dict():
    with _patch_cache_dir(), _patch_config():
        from stockpulse.data.cache import set_cached, get_cached
        data = {"price": 123.45, "volume": 1_000_000}
        set_cached("test_key_dict", data)
        assert get_cached("test_key_dict") == data


def test_round_trip_list():
    with _patch_cache_dir(), _patch_config():
        from stockpulse.data.cache import set_cached, get_cached
        data = [1, 2, 3]
        set_cached("test_key_list", data)
        assert get_cached("test_key_list") == data


# ---------------------------------------------------------------------------
# get_cached returns None for missing keys
# ---------------------------------------------------------------------------

def test_missing_key_returns_none():
    with _patch_cache_dir(), _patch_config():
        from stockpulse.data.cache import get_cached
        assert get_cached("key_that_does_not_exist") is None


# ---------------------------------------------------------------------------
# get_cached returns None for expired entries
# ---------------------------------------------------------------------------

def test_expired_entry_returns_none():
    """Entry older than TTL should be treated as a miss."""
    with _patch_cache_dir(), _patch_config():
        from stockpulse.data.cache import get_cached, _cache_path
        _TEST_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        key = "expired_key"
        path = _cache_path(key)
        # Write an entry with a timestamp 20 minutes ago (TTL = 15 min)
        entry = {"time": datetime.now() - timedelta(minutes=20), "data": "stale"}
        with open(path, "wb") as f:
            pickle.dump(entry, f)
        assert get_cached(key) is None


def test_fresh_entry_returns_data():
    """Entry within TTL should be returned."""
    with _patch_cache_dir(), _patch_config():
        from stockpulse.data.cache import get_cached, _cache_path
        _TEST_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        key = "fresh_key"
        path = _cache_path(key)
        entry = {"time": datetime.now() - timedelta(minutes=5), "data": "fresh"}
        with open(path, "wb") as f:
            pickle.dump(entry, f)
        assert get_cached(key) == "fresh"


# ---------------------------------------------------------------------------
# get_cached handles corrupt files gracefully
# ---------------------------------------------------------------------------

def test_corrupt_file_returns_none():
    with _patch_cache_dir(), _patch_config():
        from stockpulse.data.cache import get_cached, _cache_path
        _TEST_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        key = "corrupt_key"
        path = _cache_path(key)
        path.write_bytes(b"not a valid serialized file")
        assert get_cached(key) is None


# ---------------------------------------------------------------------------
# cleanup_expired_cache
# ---------------------------------------------------------------------------

def test_cleanup_removes_old_files():
    """Files older than 3x TTL should be removed."""
    with _patch_cache_dir(), _patch_config():
        from stockpulse.data.cache import cleanup_expired_cache, _cache_path
        _TEST_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        # Create a very old entry (TTL=15, so 3x=45 min; make it 60 min old)
        key = "old_entry"
        path = _cache_path(key)
        entry = {"time": datetime.now() - timedelta(minutes=60), "data": "ancient"}
        with open(path, "wb") as f:
            pickle.dump(entry, f)
        removed = cleanup_expired_cache()
        assert removed >= 1
        assert not path.exists()


def test_cleanup_keeps_fresh_files():
    """Files within 3x TTL should be kept."""
    with _patch_cache_dir(), _patch_config():
        from stockpulse.data.cache import cleanup_expired_cache, _cache_path
        _TEST_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        key = "still_good"
        path = _cache_path(key)
        entry = {"time": datetime.now() - timedelta(minutes=10), "data": "ok"}
        with open(path, "wb") as f:
            pickle.dump(entry, f)
        cleanup_expired_cache()
        assert path.exists()


def test_cleanup_removes_corrupt_files():
    with _patch_cache_dir(), _patch_config():
        from stockpulse.data.cache import cleanup_expired_cache, _cache_path
        _TEST_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        key = "corrupt_cleanup"
        path = _cache_path(key)
        path.write_bytes(b"\x00\x01\x02garbage")
        removed = cleanup_expired_cache()
        assert removed >= 1
        assert not path.exists()


def test_cleanup_returns_zero_when_no_cache_dir():
    """If cache directory doesn't exist, cleanup returns 0 without error."""
    nonexistent = Path(_TMP) / "nonexistent_dir"
    with patch("stockpulse.data.cache._CACHE_DIR", nonexistent), _patch_config():
        from stockpulse.data.cache import cleanup_expired_cache
        assert cleanup_expired_cache() == 0
