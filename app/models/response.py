from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.request import LatLng


CongestionLevel = Literal["NORMAL", "SLOW", "TRAFFIC_JAM"]


class TrafficResponse(BaseModel):
    origin: LatLng
    destination: LatLng
    duration_seconds: int
    static_duration_seconds: int
    delay_seconds: int
    congestion_level: CongestionLevel
    overall_condition: str | None
    cache_hit: bool
    queried_at: datetime
    label: str | None = None


class QuotaUsageResponse(BaseModel):
    used: int
    cap: int
    remaining: int
    reset_date: datetime


class TrafficRecordResponse(BaseModel):
    queried_at: datetime
    origin_lat: float
    origin_lng: float
    dest_lat: float
    dest_lng: float
    label: str | None
    duration_seconds: int | None
    static_duration_seconds: int | None
    delay_seconds: int | None
    congestion_level: str | None
    overall_condition: str | None
    cache_hit: bool

