from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.ai_layer import VizSpec, generate_insight, interpret_prompt, suggest_with_specs
from backend.guardrails import GuardrailViolation, validate_input
from backend.chart_engine import convert_currency_cols, render_chart
from backend.config import settings
from backend.database import get_db, init_db
from backend.ingestion import ingest_upload
from backend.models import (
    DataColumnMetadata,
    Dataset,
    Feedback,
    GeneratedOutput,
    PromptRequest as DBPromptRequest,
    User,
    VisualizationSpec as DBVisualizationSpec,
)
from backend.profiler import profile_dataframe
from backend.session_store import session_store

_SYSTEM_USER_EMAIL = "system@ai-viz-builder.internal"


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="AI Visualization Builder", lifespan=lifespan)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_or_create_system_user(db: Session) -> User:
    user = db.query(User).filter(User.email == _SYSTEM_USER_EMAIL).first()
    if user is None:
        user = User(name="System", email=_SYSTEM_USER_EMAIL, role="admin")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _parse_uuid(value: str, label: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid {label} format.")


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    session_id: str
    dataset_id: str
    file_name: str
    row_count: int
    column_count: int
    validation_report: dict[str, Any]
    schema_profile: dict[str, Any]


class PromptBody(BaseModel):
    session_id: str
    prompt: str


class PromptResponse(BaseModel):
    output_id: str
    chart_path: str
    insight: str
    viz_spec: dict[str, Any]
    alignment_issues: list[str]


class SuggestBody(BaseModel):
    session_id: str


class InterpretBody(BaseModel):
    session_id: str
    prompt: str


class InterpretResponse(BaseModel):
    chart_type: str
    x_axis: str
    y_axis: str
    aggregation: str
    title: str
    interpreted_intent: str
    filters: dict[str, Any]
    grouping: str | None
    color_encoding: str | None
    alignment_issues: list[str]


class RenderBody(BaseModel):
    session_id: str
    prompt: str
    chart_type: str
    x_axis: str
    y_axis: str
    aggregation: str
    agg_axis: str = "y"
    title: str
    filters: dict[str, Any] = {}
    grouping: str | None = None
    color_encoding: str | None = None
    interpreted_intent: str = ""
    currency_cols: list[str] = []  # columns to strip currency symbols and coerce to float


class SuggestItem(BaseModel):
    title: str
    suggestion: str
    chart_type: str
    x_axis: str
    y_axis: str
    aggregation: str
    filters: dict[str, Any] = {}
    grouping: str | None = None
    color_encoding: str | None = None


class SuggestResponse(BaseModel):
    suggestions: list[SuggestItem]


class AutoPreviewItem(BaseModel):
    output_id: str
    title: str
    suggestion: str
    chart_type: str
    x_axis: str
    y_axis: str
    aggregation: str
    filters: dict[str, Any] = {}
    grouping: str | None = None
    color_encoding: str | None = None


class AutoPreviewResponse(BaseModel):
    previews: list[AutoPreviewItem]


class FeedbackBody(BaseModel):
    output_id: str
    rating: int = Field(ge=1, le=5)
    comments: str | None = None
    revision_requested: bool = False


class FeedbackResponse(BaseModel):
    feedback_id: str


# ── GET /health ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


# ── POST /upload ───────────────────────────────────────────────────────────────

@app.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    content = await file.read()
    file_name = file.filename or "upload"

    try:
        df, report = ingest_upload(file_name, content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    profile = profile_dataframe(df)

    metadata: dict[str, Any] = {
        "validation_report": report.to_dict(),
        "schema_profile": profile.to_dict(),
        "schema_context": profile.to_llm_context(),
    }
    session_id = session_store.create(df, metadata)

    system_user = _get_or_create_system_user(db)
    ext = Path(file_name).suffix.lower().lstrip(".")
    dataset = Dataset(
        user_id=system_user.user_id,
        file_name=file_name,
        source_type=ext or "unknown",
        row_count=report.row_count,
        column_count=report.column_count,
    )
    db.add(dataset)
    db.flush()

    for col in profile.columns:
        db.add(DataColumnMetadata(
            dataset_id=dataset.dataset_id,
            column_name=col.column_name,
            detected_data_type=col.detected_type,
            null_percentage=float(col.null_percentage),
            unique_count=int(col.unique_count),
            min_value=str(col.min_value) if col.min_value is not None else None,
            max_value=str(col.max_value) if col.max_value is not None else None,
            sample_values=col.sample_values,
        ))

    db.commit()
    session_store.update_dataset_id(session_id, str(dataset.dataset_id))

    return UploadResponse(
        session_id=session_id,
        dataset_id=str(dataset.dataset_id),
        file_name=file_name,
        row_count=report.row_count,
        column_count=report.column_count,
        validation_report=report.to_dict(),
        schema_profile=profile.to_dict(),
    )


# ── POST /interpret ───────────────────────────────────────────────────────────

@app.post("/interpret", response_model=InterpretResponse)
def interpret_only(body: InterpretBody):
    """Return the AI's chart interpretation without rendering anything."""
    try:
        validate_input(body.prompt)
    except GuardrailViolation as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    session_data = session_store.get(body.session_id)
    if session_data is None:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    _, metadata = session_data
    schema_context: str = metadata.get("schema_context", "")

    try:
        spec = interpret_prompt(body.prompt, schema_context)
    except GuardrailViolation as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return InterpretResponse(**spec.to_dict())


# ── POST /render ───────────────────────────────────────────────────────────────

@app.post("/render", response_model=PromptResponse)
def render_confirmed(body: RenderBody, db: Session = Depends(get_db)):
    """Render a chart from a user-confirmed VizSpec."""
    # ── Input guardrail ────────────────────────────────────────────────────────
    try:
        validate_input(body.prompt)
    except GuardrailViolation as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    session_data = session_store.get(body.session_id)
    if session_data is None:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    df, _ = session_data
    if body.currency_cols:
        df = convert_currency_cols(df, body.currency_cols)

    db_dataset_id_str = session_store.get_dataset_id(body.session_id)
    if not db_dataset_id_str:
        raise HTTPException(status_code=400, detail="Dataset not yet persisted.")

    system_user = _get_or_create_system_user(db)

    pr = DBPromptRequest(
        user_id=system_user.user_id,
        dataset_id=uuid.UUID(db_dataset_id_str),
        prompt_text=body.prompt,
        status="processing",
        interpreted_intent=body.interpreted_intent,
    )
    db.add(pr)
    db.flush()

    viz_spec = VizSpec(
        chart_type=body.chart_type,
        x_axis=body.x_axis,
        y_axis=body.y_axis,
        aggregation=body.aggregation,
        agg_axis=body.agg_axis,
        title=body.title,
        interpreted_intent=body.interpreted_intent,
        filters=body.filters or {},
        grouping=body.grouping,
        color_encoding=body.color_encoding,
    )

    try:
        chart_result = render_chart(df, viz_spec, backend="matplotlib")
        insight = generate_insight(viz_spec, chart_result.stats)
    except Exception as exc:
        pr.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc))

    pr.status = "completed"

    db_spec = DBVisualizationSpec(
        request_id=pr.request_id,
        chart_type=viz_spec.chart_type,
        x_axis=viz_spec.x_axis,
        y_axis=viz_spec.y_axis,
        aggregation=viz_spec.aggregation,
        filters=viz_spec.filters or {},
        grouping=viz_spec.grouping,
        title=viz_spec.title,
        color_encoding=viz_spec.color_encoding,
    )
    db.add(db_spec)
    db.flush()

    output = GeneratedOutput(
        viz_id=db_spec.viz_id,
        output_path=chart_result.output_path,
        output_format="png",
        insight_summary=insight,
    )
    db.add(output)
    db.commit()

    return PromptResponse(
        output_id=str(output.output_id),
        chart_path=chart_result.output_path,
        insight=insight,
        viz_spec=viz_spec.to_dict(),
        alignment_issues=viz_spec.alignment_issues,
    )


# ── POST /suggest ─────────────────────────────────────────────────────────────

@app.post("/suggest", response_model=SuggestResponse)
def get_suggestions(body: SuggestBody):
    """Return AI chart suggestions (specs only, no rendering) based on schema/sample context."""
    session_data = session_store.get(body.session_id)
    if session_data is None:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    _, metadata = session_data
    schema_context: str = metadata.get("schema_context", "")

    try:
        specs_with_suggestions = suggest_with_specs(schema_context)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return SuggestResponse(
        suggestions=[
            SuggestItem(
                title=spec.title,
                suggestion=suggestion_text,
                chart_type=spec.chart_type,
                x_axis=spec.x_axis,
                y_axis=spec.y_axis,
                aggregation=spec.aggregation,
                filters=spec.filters or {},
                grouping=spec.grouping,
                color_encoding=spec.color_encoding,
            )
            for spec, suggestion_text in specs_with_suggestions
        ]
    )


# ── POST /auto-preview ────────────────────────────────────────────────────────

@app.post("/auto-preview", response_model=AutoPreviewResponse)
def auto_preview(body: SuggestBody, db: Session = Depends(get_db)):
    """Generate AI chart suggestions and render each as a preview thumbnail."""
    session_data = session_store.get(body.session_id)
    if session_data is None:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    df, metadata = session_data
    schema_context: str = metadata.get("schema_context", "")

    db_dataset_id_str = session_store.get_dataset_id(body.session_id)
    if not db_dataset_id_str:
        raise HTTPException(status_code=400, detail="Dataset not yet persisted — retry after upload completes.")

    system_user = _get_or_create_system_user(db)

    try:
        specs_with_suggestions = suggest_with_specs(schema_context)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if not specs_with_suggestions:
        return AutoPreviewResponse(previews=[])

    pr = DBPromptRequest(
        user_id=system_user.user_id,
        dataset_id=uuid.UUID(db_dataset_id_str),
        prompt_text="[auto-preview]",
        status="completed",
        interpreted_intent="AI-generated chart previews",
    )
    db.add(pr)
    db.flush()

    previews: list[AutoPreviewItem] = []
    for viz_spec, suggestion_text in specs_with_suggestions:
        try:
            chart_result = render_chart(df, viz_spec, backend="matplotlib")
        except Exception:
            continue

        db_spec = DBVisualizationSpec(
            request_id=pr.request_id,
            chart_type=viz_spec.chart_type,
            x_axis=viz_spec.x_axis,
            y_axis=viz_spec.y_axis,
            aggregation=viz_spec.aggregation,
            filters=viz_spec.filters or {},
            grouping=viz_spec.grouping,
            title=viz_spec.title,
            color_encoding=viz_spec.color_encoding,
        )
        db.add(db_spec)
        db.flush()

        output = GeneratedOutput(
            viz_id=db_spec.viz_id,
            output_path=chart_result.output_path,
            output_format="png",
        )
        db.add(output)
        db.flush()

        previews.append(AutoPreviewItem(
            output_id=str(output.output_id),
            title=viz_spec.title,
            suggestion=suggestion_text,
            chart_type=viz_spec.chart_type,
            x_axis=viz_spec.x_axis,
            y_axis=viz_spec.y_axis,
            aggregation=viz_spec.aggregation,
            filters=viz_spec.filters or {},
            grouping=viz_spec.grouping,
            color_encoding=viz_spec.color_encoding,
        ))

    db.commit()
    return AutoPreviewResponse(previews=previews)


# ── POST /prompt ───────────────────────────────────────────────────────────────

@app.post("/prompt", response_model=PromptResponse)
def submit_prompt(
    body: PromptBody,
    db: Session = Depends(get_db),
):
    # ── Input guardrail (before any DB writes) ─────────────────────────────────
    try:
        validate_input(body.prompt)
    except GuardrailViolation as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    session_data = session_store.get(body.session_id)
    if session_data is None:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    df, metadata = session_data
    schema_context: str = metadata.get("schema_context", "")

    db_dataset_id_str = session_store.get_dataset_id(body.session_id)
    if not db_dataset_id_str:
        raise HTTPException(status_code=400, detail="Dataset not yet persisted — retry after upload completes.")

    system_user = _get_or_create_system_user(db)

    pr = DBPromptRequest(
        user_id=system_user.user_id,
        dataset_id=uuid.UUID(db_dataset_id_str),
        prompt_text=body.prompt,
        status="processing",
    )
    db.add(pr)
    db.flush()

    try:
        viz_spec: VizSpec = interpret_prompt(body.prompt, schema_context)
        chart_result = render_chart(df, viz_spec, backend="matplotlib")
        insight = generate_insight(viz_spec, chart_result.stats)
    except GuardrailViolation as exc:
        pr.status = "failed"
        db.commit()
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        pr.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc))

    pr.interpreted_intent = viz_spec.interpreted_intent
    pr.status = "completed"

    db_spec = DBVisualizationSpec(
        request_id=pr.request_id,
        chart_type=viz_spec.chart_type,
        x_axis=viz_spec.x_axis,
        y_axis=viz_spec.y_axis,
        aggregation=viz_spec.aggregation,
        filters=viz_spec.filters or {},
        grouping=viz_spec.grouping,
        title=viz_spec.title,
        color_encoding=viz_spec.color_encoding,
    )
    db.add(db_spec)
    db.flush()

    output = GeneratedOutput(
        viz_id=db_spec.viz_id,
        output_path=chart_result.output_path,
        output_format="png",
        insight_summary=insight,
    )
    db.add(output)
    db.commit()

    return PromptResponse(
        output_id=str(output.output_id),
        chart_path=chart_result.output_path,
        insight=insight,
        viz_spec=viz_spec.to_dict(),
        alignment_issues=viz_spec.alignment_issues,
    )


# ── GET /chart/{output_id} ─────────────────────────────────────────────────────

@app.get("/chart/{output_id}")
def get_chart(output_id: str, db: Session = Depends(get_db)):
    oid = _parse_uuid(output_id, "output_id")
    output = db.query(GeneratedOutput).filter(GeneratedOutput.output_id == oid).first()
    if output is None or not output.output_path:
        raise HTTPException(status_code=404, detail="Output not found.")

    path = Path(output.output_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Chart file not found on disk.")

    return FileResponse(str(path), media_type="image/png")


# ── POST /feedback ─────────────────────────────────────────────────────────────

@app.post("/feedback", response_model=FeedbackResponse)
def submit_feedback(
    body: FeedbackBody,
    db: Session = Depends(get_db),
):
    oid = _parse_uuid(body.output_id, "output_id")
    output = db.query(GeneratedOutput).filter(GeneratedOutput.output_id == oid).first()
    if output is None:
        raise HTTPException(status_code=404, detail="Output not found.")

    system_user = _get_or_create_system_user(db)
    fb = Feedback(
        output_id=oid,
        user_id=system_user.user_id,
        rating=body.rating,
        comments=body.comments,
        revision_requested=body.revision_requested,
    )
    db.add(fb)
    db.commit()

    return FeedbackResponse(feedback_id=str(fb.feedback_id))


# ── GET /export/{output_id} ────────────────────────────────────────────────────

@app.get("/export/{output_id}")
def export_chart(
    output_id: str,
    format: str = Query(default="png", pattern="^(png|pdf)$"),
    db: Session = Depends(get_db),
):
    oid = _parse_uuid(output_id, "output_id")
    output = db.query(GeneratedOutput).filter(GeneratedOutput.output_id == oid).first()
    if output is None or not output.output_path:
        raise HTTPException(status_code=404, detail="Output not found.")

    src = Path(output.output_path)
    if not src.exists():
        raise HTTPException(status_code=404, detail="Chart file not found on disk.")

    if format == "png":
        return FileResponse(
            str(src),
            media_type="image/png",
            headers={"Content-Disposition": f'attachment; filename="{src.name}"'},
        )

    # PDF: wrap the saved PNG into a single-page PDF
    pdf_path = src.with_suffix(".pdf")
    if not pdf_path.exists():
        img = mpimg.imread(str(src))
        fig, ax = plt.subplots(figsize=(10, 7))
        ax.imshow(img)
        ax.axis("off")
        fig.savefig(str(pdf_path), format="pdf", bbox_inches="tight")
        plt.close(fig)

    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{pdf_path.name}"'},
    )
