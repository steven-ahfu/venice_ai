"""Tests for the duration and clock-time parsers used by the alarm_clock_*
operations in functions/native.py."""
import datetime
import sys

import pytest

sys.path.insert(0, ".")

# conftest.py stubs all HA modules before this runs
from custom_components.venice_ai.functions.native import (
    _parse_clock_time,
    _parse_duration_to_seconds,
)


# ── _parse_duration_to_seconds ────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    ("5 minutes", 300),
    ("5 min", 300),
    ("5m", 300),
    ("1h30m", 5400),
    ("1 hour 30 minutes", 5400),
    ("2h", 7200),
    ("90s", 90),
    ("90 seconds", 90),
    ("00:05:00", 300),
    ("01:30:00", 5400),
    ("5:00", 300),
    ("0:30", 30),
    ("45 sec", 45),
])
def test_parse_duration_known_shapes(text, expected):
    assert _parse_duration_to_seconds(text) == expected


@pytest.mark.parametrize("text", ["", "soon", "abc", "::::"])
def test_parse_duration_unparseable_returns_zero(text):
    assert _parse_duration_to_seconds(text) == 0


def test_parse_duration_mixed_units_sum():
    # Confirm units accumulate rather than overwrite.
    assert _parse_duration_to_seconds("1h 15m 30s") == 3600 + 900 + 30


# ── _parse_clock_time ─────────────────────────────────────────────────────────

def test_clock_time_iso8601_preserves_date():
    hhmm, ymd = _parse_clock_time("2026-08-15T07:30:00")
    assert hhmm == "07:30"
    assert ymd == "2026-08-15"


def test_clock_time_24h_no_date_picks_future():
    hhmm, ymd = _parse_clock_time("07:30", date_hint=None)
    assert hhmm == "07:30"
    # ymd is today or tomorrow — confirm it's not in the past.
    parsed = datetime.datetime.fromisoformat(f"{ymd}T07:30")
    assert parsed > datetime.datetime.now() - datetime.timedelta(minutes=1)


def test_clock_time_with_date_hint_used_verbatim():
    hhmm, ymd = _parse_clock_time("18:00", date_hint="2030-01-01")
    assert hhmm == "18:00"
    assert ymd == "2030-01-01"


def test_clock_time_12h_pm():
    hhmm, _ = _parse_clock_time("7:30 PM")
    assert hhmm == "19:30"


def test_clock_time_12h_am():
    hhmm, _ = _parse_clock_time("7:30 AM")
    assert hhmm == "07:30"


def test_clock_time_midnight_12am():
    hhmm, _ = _parse_clock_time("12:00 AM")
    assert hhmm == "00:00"


def test_clock_time_noon_12pm():
    hhmm, _ = _parse_clock_time("12:00 PM")
    assert hhmm == "12:00"


def test_clock_time_bare_hour():
    hhmm, _ = _parse_clock_time("6 AM")
    assert hhmm == "06:00"


def test_clock_time_empty_raises():
    with pytest.raises(ValueError, match="required"):
        _parse_clock_time("")


def test_clock_time_invalid_hour_raises():
    with pytest.raises(ValueError, match="invalid"):
        _parse_clock_time("25:00")
