"""
FastAPI integration tests using httpx.AsyncClient with ASGITransport.

All external calls (Anthropic API, chart rendering) are mocked so tests run
offline and without writing real chart files.

Note on session_store: the upload endpoint stores `str(dataset.dataset_id)` in
the session store.  With a mocked DB, the ORM default (`default=_uuid`) never
fires (it only runs at flush/INSERT time), so `dataset.dataset_id` is None.
Prompt tests therefore seed the session store directly via `valid_session` rather
than relying on the mocked upload path.
"""
from __future__ import annotations

import io
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.ai_layer import VizSpec
from backend.chart_engine import ChartResult
from backend.main import app


# ── Fixtures ───────────────────────────────────────────────────────────────────

SAMPLE_CSV = b"department,salary,headcount\nEng,90000,50\nHR,70000,20\nSales,80000,30\n"


@pytest.fixture
def mock_viz_spec() -> VizSpec:
    return VizSpec(
        chart_type="bar",
        x_axis="department",
        y_axis="salary",
        aggregation="mean",
        title="Average Salary by Department",
        interpreted_intent="Show the average salary for each department.",
    )


@pytest.fixture
def mock_chart_result(tmp_path) -> ChartResult:
    png = tmp_path / "bar_abc12345.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)  # minimal PNG-like bytes
    return ChartResult(output_path=str(png), chart_type="bar", stats={
        "row_count": 3, "y_min": 70000.0, "y_max": 90000.0,
        "y_mean": 80000.0, "y_sum": 240000.0,
    })


@pytest.fixture(autouse=True)
def _patch_db(monkeypatch):
    """Replace all DB operations with no-ops so tests need no real database."""
    from backend import main as main_mod

    fake_user = MagicMock()
    fake_user.user_id = uuid.uuid4()

    fake_dataset = MagicMock()
    fake_dataset.dataset_id = uuid.uuid4()

    fake_pr = MagicMock()
    fake_pr.request_id = uuid.uuid4()

    fake_spec = MagicMock()
    fake_spec.viz_id = uuid.uuid4()

    fake_output = MagicMock()
    fake_output.output_id = uuid.uuid4()
    fake_output.output_path = None

    fake_fb = MagicMock()
    fake_fb.feedback_id = uuid.uuid4()

    def _fake_get_or_create_system_user(db):
        return fake_user

    monkeypatch.setattr(main_mod, "_get_or_create_system_user", _fake_get_or_create_system_user)

    # Stub out the SQLAlchemy Session dependency
    fake_db = MagicMock()
    fake_db.query.return_value.filter.return_value.first.return_value = None
    fake_db.flush = MagicMock()
    fake_db.commit = MagicMock()
    fake_db.add = MagicMock()
    fake_db.refresh = MagicMock()

    from backend.database import get_db
    app.dependency_overrides[get_db] = lambda: fake_db
    yield fake_db
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def valid_session():
    """
    Seed the real session_store with a known DataFrame and dataset_id so that
    prompt tests don't depend on the mocked DB path (where dataset.dataset_id
    would be None before flush).
    """
    from backend.session_store import session_store

    df = pd.read_csv(io.BytesIO(SAMPLE_CSV))
    known_dataset_id = str(uuid.uuid4())
    metadata = {"schema_context": "Dataset: 3 rows × 3 columns"}
    session_id = session_store.create(df, metadata, dataset_id=known_dataset_id)
    yield session_id, known_dataset_id
    session_store.clear_session(session_id)


# ── GET /health ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ── POST /upload ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_csv_success(client):
    resp = await client.post(
        "/upload",
        files={"file": ("payroll.csv", SAMPLE_CSV, "text/csv")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "session_id" in body
    assert "dataset_id" in body
    assert body["row_count"] == 3
    assert body["column_count"] == 3


@pytest.mark.asyncio
async def test_upload_returns_validation_report(client):
    resp = await client.post(
        "/upload",
        files={"file": ("data.csv", SAMPLE_CSV, "text/csv")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "validation_report" in body
    assert "passed" in body["validation_report"]


@pytest.mark.asyncio
async def test_upload_returns_schema_profile(client):
    resp = await client.post(
        "/upload",
        files={"file": ("data.csv", SAMPLE_CSV, "text/csv")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "schema_profile" in body
    assert "columns" in body["schema_profile"]


@pytest.mark.asyncio
async def test_upload_unsupported_type_422(client):
    resp = await client.post(
        "/upload",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upload_empty_csv_validation_fails(client):
    empty = b"col1,col2\n"
    resp = await client.post(
        "/upload",
        files={"file": ("empty.csv", empty, "text/csv")},
    )
    # Returns 200 with validation report showing passed=False
    assert resp.status_code == 200
    assert resp.json()["validation_report"]["passed"] is False


# ── POST /prompt ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_prompt_success(client, valid_session, mock_viz_spec, mock_chart_result):
    session_id, _ = valid_session

    with patch("backend.main.interpret_prompt", return_value=mock_viz_spec), \
         patch("backend.main.render_chart", return_value=mock_chart_result), \
         patch("backend.main.generate_insight", return_value="Sales peaked in Engineering."):
        resp = await client.post(
            "/prompt",
            json={"session_id": session_id, "prompt": "Show salary by department"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "output_id" in body
    assert "insight" in body
    assert "viz_spec" in body


@pytest.mark.asyncio
async def test_prompt_returns_viz_spec_fields(client, valid_session, mock_viz_spec, mock_chart_result):
    session_id, _ = valid_session

    with patch("backend.main.interpret_prompt", return_value=mock_viz_spec), \
         patch("backend.main.render_chart", return_value=mock_chart_result), \
         patch("backend.main.generate_insight", return_value="Insight."):
        resp = await client.post(
            "/prompt",
            json={"session_id": session_id, "prompt": "Show salary by department"},
        )

    spec = resp.json()["viz_spec"]
    assert spec["chart_type"] == "bar"
    assert spec["x_axis"] == "department"
    assert spec["y_axis"] == "salary"


@pytest.mark.asyncio
async def test_prompt_expired_session_404(client):
    resp = await client.post(
        "/prompt",
        json={"session_id": str(uuid.uuid4()), "prompt": "Show anything"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_prompt_ai_failure_500(client, valid_session):
    session_id, _ = valid_session

    with patch("backend.main.interpret_prompt", side_effect=RuntimeError("API down")):
        resp = await client.post(
            "/prompt",
            json={"session_id": session_id, "prompt": "Show salary"},
        )

    assert resp.status_code == 500


# ── GET /chart/{output_id} ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_chart_not_found(client, _patch_db):
    _patch_db.query.return_value.filter.return_value.first.return_value = None
    resp = await client.get(f"/chart/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_chart_invalid_uuid_422(client):
    resp = await client.get("/chart/not-a-uuid")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_chart_returns_png(client, _patch_db, tmp_path):
    png = tmp_path / "chart.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

    fake_output = MagicMock()
    fake_output.output_path = str(png)
    _patch_db.query.return_value.filter.return_value.first.return_value = fake_output

    resp = await client.get(f"/chart/{uuid.uuid4()}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/png")


# ── POST /feedback ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_feedback_success(client, _patch_db):
    fake_output = MagicMock()
    fake_output.output_id = uuid.uuid4()
    fake_fb = MagicMock()
    fake_fb.feedback_id = uuid.uuid4()

    call_count = 0

    def _first_side_effect():
        nonlocal call_count
        call_count += 1
        return fake_output if call_count == 1 else None

    _patch_db.query.return_value.filter.return_value.first.return_value = fake_output

    # We need the Feedback ORM object to have feedback_id set after db.add
    def _add_side_effect(obj):
        if hasattr(obj, "feedback_id") and obj.feedback_id is None:
            obj.feedback_id = uuid.uuid4()

    _patch_db.add.side_effect = _add_side_effect

    resp = await client.post(
        "/feedback",
        json={
            "output_id": str(uuid.uuid4()),
            "rating": 4,
            "comments": "Great chart!",
            "revision_requested": False,
        },
    )
    assert resp.status_code == 200
    assert "feedback_id" in resp.json()


@pytest.mark.asyncio
async def test_feedback_rating_out_of_range(client):
    resp = await client.post(
        "/feedback",
        json={"output_id": str(uuid.uuid4()), "rating": 6},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_feedback_invalid_uuid_422(client):
    resp = await client.post(
        "/feedback",
        json={"output_id": "not-a-uuid", "rating": 3},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_feedback_output_not_found_404(client, _patch_db):
    _patch_db.query.return_value.filter.return_value.first.return_value = None
    resp = await client.post(
        "/feedback",
        json={"output_id": str(uuid.uuid4()), "rating": 3},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_feedback_no_comments(client, _patch_db):
    fake_output = MagicMock()
    _patch_db.query.return_value.filter.return_value.first.return_value = fake_output

    def _add_side_effect(obj):
        if hasattr(obj, "feedback_id"):
            obj.feedback_id = uuid.uuid4()

    _patch_db.add.side_effect = _add_side_effect

    resp = await client.post(
        "/feedback",
        json={"output_id": str(uuid.uuid4()), "rating": 5},
    )
    assert resp.status_code == 200


# ── GET /export/{output_id} ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_invalid_uuid_422(client):
    resp = await client.get("/export/not-a-uuid")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_export_not_found_404(client, _patch_db):
    _patch_db.query.return_value.filter.return_value.first.return_value = None
    resp = await client.get(f"/export/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_export_png_returns_attachment(client, _patch_db, tmp_path):
    png = tmp_path / "chart.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

    fake_output = MagicMock()
    fake_output.output_path = str(png)
    _patch_db.query.return_value.filter.return_value.first.return_value = fake_output

    resp = await client.get(f"/export/{uuid.uuid4()}?format=png")
    assert resp.status_code == 200
    assert "attachment" in resp.headers.get("content-disposition", "")


@pytest.mark.asyncio
async def test_export_invalid_format_422(client):
    resp = await client.get(f"/export/{uuid.uuid4()}?format=gif")
    assert resp.status_code == 422
