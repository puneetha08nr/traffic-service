from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Double, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TrafficRecord(Base):
    __tablename__ = "traffic_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    queried_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    origin_lat: Mapped[float] = mapped_column(Double, nullable=False)
    origin_lng: Mapped[float] = mapped_column(Double, nullable=False)
    dest_lat: Mapped[float] = mapped_column(Double, nullable=False)
    dest_lng: Mapped[float] = mapped_column(Double, nullable=False)

    label: Mapped[str | None] = mapped_column(Text, nullable=True)

    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    static_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delay_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    congestion_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    overall_condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

