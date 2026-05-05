from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


# ── 1. User ────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    user_id:   Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name:      Mapped[str]       = mapped_column(String(255), nullable=False)
    email:     Mapped[str]       = mapped_column(String(255), unique=True, nullable=False)
    role:      Mapped[str]       = mapped_column(String(50), nullable=False, default="viewer")

    datasets:        Mapped[list[Dataset]]       = relationship("Dataset", back_populates="user")
    prompt_requests: Mapped[list[PromptRequest]] = relationship("PromptRequest", back_populates="user")
    feedbacks:       Mapped[list[Feedback]]      = relationship("Feedback", back_populates="user")


# ── 2. Dataset ─────────────────────────────────────────────────────────────────

class Dataset(Base):
    __tablename__ = "datasets"

    dataset_id:       Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id:          Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    file_name:        Mapped[str]       = mapped_column(String(255), nullable=False)
    source_type:      Mapped[str]       = mapped_column(String(20), nullable=False)   # csv | xlsx | json | parquet
    upload_timestamp: Mapped[datetime]  = mapped_column(DateTime(timezone=True), default=_now)
    row_count:        Mapped[int | None]= mapped_column(Integer)
    column_count:     Mapped[int | None]= mapped_column(Integer)
    schema_version:   Mapped[int]       = mapped_column(Integer, default=1)

    user:            Mapped[User]                    = relationship("User", back_populates="datasets")
    columns:         Mapped[list[DataColumnMetadata]]= relationship("DataColumnMetadata", back_populates="dataset", cascade="all, delete-orphan")
    prompt_requests: Mapped[list[PromptRequest]]     = relationship("PromptRequest", back_populates="dataset")


# ── 3. DataColumnMetadata ──────────────────────────────────────────────────────

class DataColumnMetadata(Base):
    __tablename__ = "data_column_metadata"

    column_id:         Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    dataset_id:        Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), ForeignKey("datasets.dataset_id"), nullable=False)
    column_name:       Mapped[str]          = mapped_column(String(255), nullable=False)
    detected_data_type:Mapped[str | None]   = mapped_column(String(50))   # numeric | categorical | datetime | boolean
    null_percentage:   Mapped[float | None] = mapped_column(Float)
    unique_count:      Mapped[int | None]   = mapped_column(Integer)
    min_value:         Mapped[str | None]   = mapped_column(String(255))  # stored as string to handle dates & numbers
    max_value:         Mapped[str | None]   = mapped_column(String(255))
    sample_values:     Mapped[list | None]  = mapped_column(JSONB)        # e.g. ["West", "East", "North"]

    dataset: Mapped[Dataset] = relationship("Dataset", back_populates="columns")


# ── 4. PromptRequest ───────────────────────────────────────────────────────────

class PromptRequest(Base):
    __tablename__ = "prompt_requests"

    request_id:         Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id:            Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    dataset_id:         Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("datasets.dataset_id"), nullable=False)
    prompt_text:        Mapped[str]       = mapped_column(Text, nullable=False)
    request_timestamp:  Mapped[datetime]  = mapped_column(DateTime(timezone=True), default=_now)
    interpreted_intent: Mapped[str | None]= mapped_column(Text)
    status:             Mapped[str]       = mapped_column(String(20), default="pending")  # pending | processing | completed | failed

    user:    Mapped[User]    = relationship("User", back_populates="prompt_requests")
    dataset: Mapped[Dataset] = relationship("Dataset", back_populates="prompt_requests")
    viz_specs: Mapped[list[VisualizationSpec]] = relationship("VisualizationSpec", back_populates="prompt_request")


# ── 5. VisualizationSpec ──────────────────────────────────────────────────────

class VisualizationSpec(Base):
    __tablename__ = "visualization_specs"

    viz_id:        Mapped[uuid.UUID]   = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    request_id:    Mapped[uuid.UUID]   = mapped_column(UUID(as_uuid=True), ForeignKey("prompt_requests.request_id"), nullable=False)
    chart_type:    Mapped[str | None]  = mapped_column(String(50))    # bar | line | scatter | pie | histogram
    x_axis:        Mapped[str | None]  = mapped_column(String(255))
    y_axis:        Mapped[str | None]  = mapped_column(String(255))
    aggregation:   Mapped[str | None]  = mapped_column(String(50))    # sum | mean | count | max | min
    filters:       Mapped[dict | None] = mapped_column(JSONB)         # e.g. {"region": "West"}
    grouping:      Mapped[str | None]  = mapped_column(String(255))
    title:         Mapped[str | None]  = mapped_column(String(500))
    color_encoding:Mapped[str | None]  = mapped_column(String(255))

    prompt_request: Mapped[PromptRequest]        = relationship("PromptRequest", back_populates="viz_specs")
    outputs:        Mapped[list[GeneratedOutput]] = relationship("GeneratedOutput", back_populates="viz_spec")


# ── 6. GeneratedOutput ─────────────────────────────────────────────────────────

class GeneratedOutput(Base):
    __tablename__ = "generated_outputs"

    output_id:          Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    viz_id:             Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("visualization_specs.viz_id"), nullable=False)
    output_path:        Mapped[str | None]= mapped_column(String(1000))
    output_format:      Mapped[str | None]= mapped_column(String(10))   # png | pdf
    generated_timestamp:Mapped[datetime]  = mapped_column(DateTime(timezone=True), default=_now)
    insight_summary:    Mapped[str | None]= mapped_column(Text)

    viz_spec:  Mapped[VisualizationSpec] = relationship("VisualizationSpec", back_populates="outputs")
    feedbacks: Mapped[list[Feedback]]    = relationship("Feedback", back_populates="output")


# ── 7. Feedback ────────────────────────────────────────────────────────────────

class Feedback(Base):
    __tablename__ = "feedbacks"

    feedback_id:       Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    output_id:         Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), ForeignKey("generated_outputs.output_id"), nullable=False)
    user_id:           Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    rating:            Mapped[int | None] = mapped_column(Integer)          # 1–5
    comments:          Mapped[str | None] = mapped_column(Text)
    revision_requested:Mapped[bool]       = mapped_column(Boolean, default=False)

    output: Mapped[GeneratedOutput] = relationship("GeneratedOutput", back_populates="feedbacks")
    user:   Mapped[User]            = relationship("User", back_populates="feedbacks")
