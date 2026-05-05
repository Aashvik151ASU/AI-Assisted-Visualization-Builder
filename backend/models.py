from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from backend.database import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


# ── Feedback ───────────────────────────────────────────────────────────────────
# Standalone table — no foreign keys to other tables.
# Captures user star-ratings and optional comments for each rendered chart.

class Feedback(Base):
    __tablename__ = "feedbacks"

    feedback_id:       Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    output_id:         Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), nullable=False)   # local chart UUID, no FK
    session_id:        Mapped[str | None] = mapped_column(String(255))                          # session that produced the chart
    rating:            Mapped[int]        = mapped_column(Integer, nullable=False)               # 1–5
    comments:          Mapped[str | None] = mapped_column(Text)
    revision_requested:Mapped[bool]       = mapped_column(Boolean, default=False)
    chart_type:        Mapped[str | None] = mapped_column(String(50))                           # bar | line | scatter | pie | histogram
    chart_title:       Mapped[str | None] = mapped_column(String(500))
    submitted_at:      Mapped[datetime]   = mapped_column(DateTime(timezone=True), server_default=func.now())
