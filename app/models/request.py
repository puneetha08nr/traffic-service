from __future__ import annotations

from pydantic import BaseModel, Field


class LatLng(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class TrafficQueryRequest(BaseModel):
    origin: LatLng
    destination: LatLng
    label: str | None = None


class TrafficHistoryQuery(BaseModel):
    origin_lat: float
    origin_lng: float
    dest_lat: float
    dest_lng: float
    from_dt: str
    to_dt: str
    limit: int = 100

