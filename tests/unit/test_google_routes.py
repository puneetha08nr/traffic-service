from __future__ import annotations

import pytest

from app.core.google_routes import GoogleRoutesClient
from app.core.exceptions import GoogleRoutesAPIError


class DummyResp:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class DummyHttpx:
    def __init__(self, resp: DummyResp):
        self._resp = resp

    async def post(self, *args, **kwargs):
        return self._resp

    async def head(self, *args, **kwargs):
        return DummyResp(200, {})


@pytest.mark.anyio
async def test_google_routes_parse_basic():
    payload = {
        "routes": [
            {
                "duration": "120s",
                "staticDuration": "100s",
                "travelAdvisory": {"trafficOnRoute": "HEAVY_TRAFFIC"},
            }
        ]
    }
    client = GoogleRoutesClient(httpx_client=DummyHttpx(DummyResp(200, payload)), api_key="k")  # type: ignore[arg-type]
    res = await client.compute_route(1.0, 2.0, 3.0, 4.0)
    assert res.duration_seconds == 120
    assert res.static_duration_seconds == 100
    assert res.delay_seconds == 20
    assert res.congestion_level == "NORMAL"
    assert res.overall_condition == "HEAVY_TRAFFIC"


@pytest.mark.anyio
async def test_google_routes_error_on_no_routes():
    payload = {"routes": []}
    client = GoogleRoutesClient(httpx_client=DummyHttpx(DummyResp(200, payload)), api_key="k")  # type: ignore[arg-type]
    with pytest.raises(GoogleRoutesAPIError):
        await client.compute_route(1.0, 2.0, 3.0, 4.0)

