from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.exceptions import GoogleRoutesAPIError
from app.utils.logger import get_logger, log_extra


logger = get_logger(__name__)

CongestionLevel = Literal["NORMAL", "SLOW", "TRAFFIC_JAM"]


@dataclass(frozen=True)
class GoogleRouteResult:
    duration_seconds: int
    static_duration_seconds: int
    delay_seconds: int
    congestion_level: CongestionLevel
    overall_condition: str | None
    raw_response: dict[str, Any]
    queried_at: datetime


def _parse_duration_seconds(value: Any) -> int:
    # Google returns duration like "123s"
    if isinstance(value, str) and value.endswith("s"):
        try:
            return int(float(value[:-1]))
        except ValueError:
            return 0
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def _congestion_from_delay(delay_seconds: int) -> CongestionLevel:
    if delay_seconds < 60:
        return "NORMAL"
    if delay_seconds <= 300:
        return "SLOW"
    return "TRAFFIC_JAM"


class GoogleRoutesClient:
    BASE_URL = "https://routes.googleapis.com"
    PATH = "/directions/v2:computeRoutes"

    def __init__(self, httpx_client: httpx.AsyncClient, api_key: str) -> None:
        self._client = httpx_client
        self._api_key = api_key

    async def ping(self) -> None:
        # Best-effort reachability check: just open TCP/TLS to host by doing a HEAD on base.
        await self._client.head(self.BASE_URL, headers={"X-Goog-Api-Key": self._api_key})

    @retry(
        wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def compute_route(self, origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> GoogleRouteResult:
        url = f"{self.BASE_URL}{self.PATH}"
        body = {
            "origin": {
                "location": {
                    "latLng": {"latitude": origin_lat, "longitude": origin_lng}
                }
            },
            "destination": {
                "location": {"latLng": {"latitude": dest_lat, "longitude": dest_lng}}
            },
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
            "extraComputations": ["TRAFFIC_ON_POLYLINE"],
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": (
                "routes.duration,"
                "routes.staticDuration,"
                "routes.travelAdvisory,"
                "routes.legs.travelAdvisory,"
                "routes.legs.steps.localizedValues"
            ),
        }

        start = datetime.now(timezone.utc)
        
        # --- ADD THE PRINT HERE, right before the network call ---
        print(f"\n---> DEBUG: Using API Key starting with: '{self._api_key[:10]}...' <--- \n", flush=True)

        # Sanity check: verify API key is present (prefix only).
        logger.info(
            "google_api_key_prefix",
            extra=log_extra(api_key_prefix=(self._api_key or "")[:10]),
        )
        
        try:
            resp = await self._client.post(url, json=body, headers=headers)
        except httpx.HTTPError as e:
            raise GoogleRoutesAPIError(f"HTTP error calling Google Routes API: {e!s}") from e
            
        # (Remove the old print from down here)
        
        if resp.status_code >= 400:
            raise GoogleRoutesAPIError(
                f"Google Routes API returned {resp.status_code}: {resp.text}"
            )

        data = resp.json()
        parsed = self._parse(data)
        duration_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
        logger.info(
            "google_routes_call",
            extra=log_extra(
                origin_lat=round(origin_lat, 4),
                origin_lng=round(origin_lng, 4),
                dest_lat=round(dest_lat, 4),
                dest_lng=round(dest_lng, 4),
                duration_ms=duration_ms,
                congestion_level=parsed.congestion_level,
            ),
        )
        return parsed

    def _parse(self, payload: dict[str, Any]) -> GoogleRouteResult:
        routes = payload.get("routes") or []
        if not routes:
            raise GoogleRoutesAPIError("Google Routes response missing routes[].")

        r0 = routes[0] or {}
        duration = _parse_duration_seconds(r0.get("duration"))
        static_duration = _parse_duration_seconds(r0.get("staticDuration"))
        delay = max(0, duration - static_duration)

        travel_adv = r0.get("travelAdvisory") or {}
        overall = travel_adv.get("trafficOnRoute")

        congestion_level = _congestion_from_delay(delay)

        return GoogleRouteResult(
            duration_seconds=int(duration),
            static_duration_seconds=int(static_duration),
            delay_seconds=int(delay),
            congestion_level=congestion_level,
            overall_condition=overall,
            raw_response=payload,
            queried_at=datetime.now(timezone.utc),
        )

