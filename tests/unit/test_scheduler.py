from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.request import LatLng, TrafficQueryRequest
from app.models.response import TrafficResponse
from app.scheduler import MG_ROAD_REQUEST, poll_mg_road, start_scheduler, stop_scheduler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_traffic_response(**overrides) -> TrafficResponse:
    defaults = dict(
        origin=LatLng(latitude=12.9752, longitude=77.6094),
        destination=LatLng(latitude=12.9719, longitude=77.6176),
        duration_seconds=347,
        static_duration_seconds=412,
        delay_seconds=0,
        congestion_level="NORMAL",
        overall_condition=None,
        cache_hit=False,
        queried_at=datetime(2026, 3, 30, 8, 29, 12, tzinfo=timezone.utc),
        label="mg_road_metro_to_trinity",
    )
    defaults.update(overrides)
    return TrafficResponse(**defaults)


# ---------------------------------------------------------------------------
# poll_mg_road — calls _do_poll correctly
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_poll_mg_road_calls_do_poll_with_app():
    mock_app = MagicMock()
    expected = _make_traffic_response()

    with patch("app.scheduler._do_poll", new=AsyncMock(return_value=expected)) as mock_do_poll:
        await poll_mg_road(mock_app)

    mock_do_poll.assert_awaited_once_with(mock_app)


@pytest.mark.anyio
async def test_poll_mg_road_passes_mg_road_request():
    """_do_poll receives the app; the fixed MG Road request is embedded inside _do_poll."""
    mock_app = MagicMock()
    expected = _make_traffic_response()

    with patch("app.scheduler._do_poll", new=AsyncMock(return_value=expected)):
        await poll_mg_road(mock_app)

    # Verify the constant request has the right coordinates
    assert MG_ROAD_REQUEST.origin.latitude == 12.9752
    assert MG_ROAD_REQUEST.origin.longitude == 77.6094
    assert MG_ROAD_REQUEST.destination.latitude == 12.9719
    assert MG_ROAD_REQUEST.destination.longitude == 77.6176
    assert MG_ROAD_REQUEST.label == "mg_road_metro_to_trinity"


# ---------------------------------------------------------------------------
# poll_mg_road — exception handling
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_poll_mg_road_swallows_exception():
    """A failing _do_poll must not propagate — the scheduler must keep running."""
    mock_app = MagicMock()

    with patch("app.scheduler._do_poll", new=AsyncMock(side_effect=RuntimeError("network down"))):
        # Should not raise
        await poll_mg_road(mock_app)


@pytest.mark.anyio
async def test_poll_mg_road_swallows_any_exception_type():
    mock_app = MagicMock()

    for exc_class in (ValueError, ConnectionError, TimeoutError, Exception):
        with patch("app.scheduler._do_poll", new=AsyncMock(side_effect=exc_class("boom"))):
            await poll_mg_road(mock_app)  # must not raise


# ---------------------------------------------------------------------------
# start / stop lifecycle
# ---------------------------------------------------------------------------

def test_start_scheduler_returns_running_scheduler():
    mock_app = MagicMock()
    scheduler = start_scheduler(mock_app, interval_minutes=5)
    try:
        assert scheduler.running
        job = scheduler.get_job("mg_road_poll")
        assert job is not None
        assert job.id == "mg_road_poll"
    finally:
        scheduler.shutdown(wait=False)


def test_start_scheduler_registers_job_with_correct_interval():
    mock_app = MagicMock()
    scheduler = start_scheduler(mock_app, interval_minutes=10)
    try:
        job = scheduler.get_job("mg_road_poll")
        # APScheduler stores interval trigger fields
        assert job.trigger.interval.total_seconds() == 600  # 10 * 60
    finally:
        scheduler.shutdown(wait=False)


def test_stop_scheduler_shuts_down():
    mock_app = MagicMock()
    scheduler = start_scheduler(mock_app, interval_minutes=1)
    assert scheduler.running
    stop_scheduler()
    assert not scheduler.running


def test_stop_scheduler_is_idempotent():
    """Calling stop when already stopped must not raise."""
    stop_scheduler()
    stop_scheduler()
