# Build Checkpoints: AI-Assisted Visualization Builder

## Checkpoint 1 — Project Scaffold & Environment
**Status:** Complete

Set up the folder structure, `requirements.txt`, and config. Created top-level directories: `backend/`, `frontend/`, `data/` (with `uploads/`, `outputs/`, `samples/`), and `tests/`. Initialized a `.env.example` for the Claude API key, a `pydantic-settings`-based `config.py`, a SQLAlchemy `database.py` stub, a minimal FastAPI `main.py` (`/health`), a Streamlit `frontend/app.py` stub, and placeholder stubs for every backend module. All dependencies installed into a Python 3.12 virtual environment (`.venv`).

---

## Checkpoint 2 — Data Ingestion & Validation Layer
**Status:** Complete

Build the file upload parser (`ingestion.py`) that accepts CSV, XLSX, and JSON, loads them into Pandas DataFrames, and runs the following validation checks:
- File type and size validation
- Schema validation (consistent headers, readable structure)
- Null value percentage per column
- Duplicate record detection
- Data type inference and standardization
- Range validation (e.g. no negative salaries)
- Date format detection and standardization

Output: a clean Pandas DataFrame and a structured validation report dictionary.

---

## Checkpoint 3 — Schema Profiling Engine
**Status:** Complete

Build the profiler (`profiler.py`) that scans a loaded DataFrame and generates column-level metadata:
- Detected data type (numeric, categorical, datetime, boolean)
- Null percentage
- Unique value count
- Min / max values
- Sample values (up to 5)
- Descriptive statistics for numeric columns

This metadata is stored separately and passed to the AI layer so the prompt interpretation layer understands the dataset structure before recommending charts.

---

## Checkpoint 4 — Database & Metadata Storage (Supabase / PostgreSQL)
**Status:** Complete

Set up Supabase (PostgreSQL) with SQLAlchemy ORM models for all 7 entities defined in the README data model:
1. **User** — user_id, name, email, role
2. **Dataset** — dataset_id, user_id, file_name, source_type, upload_timestamp, row_count, column_count, schema_version
3. **DataColumnMetadata** — column_id, dataset_id, column_name, detected_data_type, null_percentage, unique_count, min_value, max_value, sample_values
4. **PromptRequest** — request_id, user_id, dataset_id, prompt_text, request_timestamp, interpreted_intent, status
5. **VisualizationSpec** — viz_id, request_id, chart_type, x_axis, y_axis, aggregation, filters, grouping, title, color_encoding
6. **GeneratedOutput** — output_id, viz_id, output_path, output_format, generated_timestamp, insight_summary
7. **Feedback** — feedback_id, output_id, user_id, rating, comments, revision_requested

Uses UUID primary keys and JSONB columns for flexible fields (sample_values, filters). Also includes `init_db()` (`Base.metadata.create_all`) and `check_connection()` helpers in `database.py`.

---

## Checkpoint 5 — Claude API: Prompt Interpretation Layer
**Status:** Complete

Wire up the Claude API (`ai_layer.py`) to receive a user's natural language prompt combined with the dataset's schema metadata, and return a structured `VisualizationSpec`:
- Chart type (bar, line, scatter, pie, histogram, etc.)
- X-axis column
- Y-axis column
- Aggregation function (sum, mean, count, etc.)
- Filters (if any)
- Grouping column (if any)
- Suggested chart title
- Prompt-to-data alignment check (flag missing columns, suggest closest matches)

Uses prompt caching to reduce API cost for repeated schema context calls.

---

## Checkpoint 6 — Chart Generation Engine
**Status:** Complete

Build `chart_engine.py` using Matplotlib and Plotly that consumes a `VisualizationSpec` and the cleaned DataFrame to render a chart. Supported chart types:
- Bar chart
- Line chart
- Scatter plot
- Pie chart
- Histogram

Applies any aggregation and filtering specified in the spec, then saves the rendered output as a PNG file to `data/outputs/`. Returns the output file path and basic chart statistics.

---

## Checkpoint 7 — Insight Summary Generation
**Status:** Complete

Add a second Claude API call (`ai_layer.py`) that takes the rendered chart spec plus computed data statistics (min, max, mean, trend direction, top categories) and returns a 2–3 sentence natural language insight summary. The summary is stored in the `GeneratedOutput` record and displayed alongside the chart in the UI.

---

## Checkpoint 8 — FastAPI Backend
**Status:** Complete

Wire all modules together into the FastAPI application (`main.py`) with the following endpoints:
- `POST /upload` — accept file, run ingestion + profiling, save dataset metadata to DB, return dataset_id
- `POST /prompt` — accept dataset_id + prompt text, call AI layer, generate chart, save all records, return chart path + insight
- `GET /chart/{output_id}` — retrieve a previously generated chart image
- `POST /feedback` — submit a rating and optional revision comment for an output
- `GET /export/{output_id}` — download chart as PNG or PDF

Includes Pydantic request/response schemas and dependency-injected DB sessions.

---

## Checkpoint 9 — Frontend (Streamlit UI)
**Status:** Complete

Build the full Streamlit application (`frontend/app.py`) with:
- File upload widget (CSV, XLSX, JSON and Parquet)
- Data preview table and validation report display
- Schema metadata panel (column types, null %, sample values)
- Natural language prompt text box
- Chart display area (rendered PNG or interactive Plotly chart)
- Insight summary panel below the chart
- Thumbs up / thumbs down feedback buttons
- Refine prompt input for iterative chart improvement
- PNG / PDF export download button

---

## Checkpoint 10 — End-to-End Testing & Sample Data
**Status:** Complete

Add a `tests/` suite covering all major modules:
- `test_ingestion.py` — file parsing, validation checks, error handling
- `test_profiler.py` — schema detection accuracy, metadata output shape
- `test_chart_engine.py` — chart rendering for each supported type
- `test_api.py` — FastAPI endpoint integration tests using `httpx`

Also drop three sample business datasets into `data/samples/` for demo use:
- `payroll_sample.csv` — department, employee count, salary, overtime hours
- `sales_sample.csv` — region, product, monthly revenue, units sold
- `hr_sample.csv` — department, attrition rate, headcount, region

---

## Checkpoint 11 — AI-Assisted Two-Path Visualization Workflow
**Status:** Complete

Replaced the original single-tab prompt-only UI with a two-tab visualization workflow. Both paths render charts against the **full uploaded dataset** using Matplotlib as the default backend.

### Design principle
The AI only ever sees schema metadata and sample values — never the raw full dataset. Full-dataset access happens exclusively at render time, regardless of which path triggered it.

### Tab 1 — AI Suggestions
- User clicks **Get AI Suggestions**; the backend calls `suggest_with_specs`, which sends the schema/sample context to Claude and returns up to 5 structured chart specs (chart type, X/Y columns, aggregation, title, plain-English description).
- Suggestions are displayed as info cards in a grid (up to 3 columns): chart type badge, X/Y/aggregation metadata, and suggestion sentence.
- Clicking **Use This Chart** calls `POST /render` with the suggested spec — the chart is rendered immediately against the full uploaded dataset, with no intermediate confirmation step.
- A **Refresh Suggestions** button lets users re-generate a new set of ideas.

### Tab 2 — Build Your Own
Full manual control over every chart parameter:
- Chart type (bar, line, scatter, pie, histogram)
- X-axis and Y-axis column selectors
- Aggregation function (sum, mean, count, max, min, none)
- **"Apply aggregation to"** dropdown (Y-axis / X-axis) — controls which column the aggregation function operates on:
  - **Y-axis (default):** group by X column, aggregate Y values — e.g. `sum(revenue) by region`
  - **X-axis:** group by Y column, aggregate X values — e.g. `mean(age) by department`
- **Group By** selector — splits the chart into separate coloured series by a chosen column
- **Filters expander** — up to 3 simultaneous column-value filters applied before rendering:
  - Categorical columns → multiselect from known top categories (supports multiple values via `isin`)
  - Numeric / datetime / other → free-text exact-match input
  - Active filters summarised inline before the Generate button
- Optional chart title (auto-generated if left blank)
- **Generate Chart** button renders on the full dataset

### Amount / Currency Column Conversion
A **💱 Amount / Currency Columns** expander sits between the schema panel and the visualization tabs. On every file upload the app scans sample values for currency symbols (`$€£¥₹₩₺₽`) and auto-detects matching columns; the expander opens automatically and those columns are pre-selected. Users can add or remove columns at any time. Every chart render — from either tab — strips the symbol and thousands commas from the selected columns and coerces them to `float` before any filtering or aggregation.

### Shared output area (below tabs)
Chart image, AI-generated insight summary, PNG/PDF export buttons (including active filter and group-by metadata in the spec expander), and a star-rating feedback form all appear below the tabs and are populated by whichever path last produced a result.

### File changes
**`frontend/app.py`**
- Two-tab layout replacing the previous single manual-builder section
- `_call_suggest` helper hits `POST /suggest`; suggestion cards rendered in a column grid
- "Use This Chart" calls `_render_confirmed` directly; no pre-fill intermediate step
- `_apply_chart_result` cleaned up (removed stale `pending_spec`/`pending_prompt` references)
- Session state: `ai_suggestions`, `ai_suggestions_loaded` (replaces `auto_previews*`); `currency_cols` (auto-set on upload)
- `_detect_currency_cols(schema_profile)` helper scans sample values for currency symbols
- Group By selectbox and Filters expander (3 rows, type-aware value widgets) added to Build Your Own tab
- `_render_confirmed` accepts `currency_cols` parameter; both render call-sites pass `st.session_state.currency_cols`

**`backend/main.py`**
- `POST /suggest` endpoint — schema/sample only, returns `SuggestResponse`; no `render_chart` call
- `SuggestItem` and `SuggestResponse` Pydantic models added
- `agg_axis: str = "y"` and `currency_cols: list[str] = []` added to `RenderBody`
- `agg_axis` passed through to `VizSpec`; `currency_cols` triggers `convert_currency_cols` on the DataFrame before rendering
- All three rendering endpoints (`/render`, `/prompt`, `/auto-preview`) use `backend="matplotlib"` explicitly

**`backend/ai_layer.py`**
- `agg_axis: str = "y"` field added to `VizSpec` dataclass and `to_dict()`

**`backend/chart_engine.py`**
- Default `backend` parameter changed from `"plotly"` to `"matplotlib"`
- `_apply_aggregation` refactored to return `(plot_df, eff_x, eff_y)` 3-tuple; `spec.agg_axis` determines which column is the grouping dimension vs. the aggregated measure
- `_render_figure`, `_render_figure_matplotlib`, and `_compute_stats` updated to accept and use `eff_x` / `eff_y` parameters directly
- `_apply_filters` updated to support list values (`isin`) in addition to single-value equality matches
- `convert_currency_cols(df, cols)` added — strips `[$€£¥₹₩₺₽,\s]` via compiled regex and coerces to `float`

---

## Checkpoint 12 — Group By, Filters, and Currency Amount Conversion
**Status:** Complete

Extended the **Build Your Own** tab with three new data-shaping controls and added a global currency-conversion step that applies to both chart paths.

### Group By
A **Group By** selectbox (default: none) lets users split any chart into separate series or colour groups by a chosen column. The value is passed as `grouping` in the render payload and fed into `_group_cols()` inside the aggregation logic, producing grouped bar clusters, multi-series lines, or colour-coded scatter plots.

### Filters
A collapsible **Filters** expander exposes up to 3 simultaneous column-value filters:
- **Categorical columns** — multiselect populated from the column's known top categories; selecting multiple values produces an `isin` filter
- **Numeric / datetime / other** — free-text input for an exact-match equality filter
- All active filters are ANDed together and applied to the full dataset before aggregation
- `_apply_filters` in `chart_engine.py` updated to handle both single strings (equality) and lists (isin)

### Amount / Currency Column Conversion
- On file upload, `_detect_currency_cols` scans each column's sample values for `$€£¥₹₩₺₽` and auto-selects matching columns
- A **💱 Amount / Currency Columns** expander (auto-expanded when columns are detected) lets users confirm or change the selection
- `currency_cols: list[str] = []` added to `RenderBody`; the `/render` endpoint calls `convert_currency_cols(df, body.currency_cols)` before any filtering or rendering
- `convert_currency_cols` in `chart_engine.py` strips symbols and commas with a compiled regex then coerces to `float`; non-parseable values become `NaN`
- Conversion applies to **both** the AI Suggestions path and the Build Your Own path

---

## Checkpoint 13 — Chart Layout Improvements & Complete Filter Values
**Status:** Complete

### Chart layout fixes (`backend/chart_engine.py`)

Rewrote `_render_figure_matplotlib` to eliminate congested axes and overlapping legends:

- **Per-chart figure creation**: each chart type now creates its own `fig, ax` with type-appropriate dimensions instead of a shared fixed `(10, 6)` size.
- **Bar chart — dynamic width**: figure width scales with the number of unique X values — `max(10, min(n_bars * 0.55, 36))` — so wide datasets expand the canvas rather than squashing labels. Labels rotate 90° when there are more than 20 bars, 45° otherwise.
- **Line chart**: default size increased to `(13, 7)` for more horizontal breathing room.
- **Pie chart — legend for dense slices**: when there are more than 10 slices, per-slice labels are removed from the wedges and moved into a legend anchored to the right of the chart. `bbox_inches="tight"` (already used in `savefig`) ensures the legend is included in the PNG without clipping.
- **Charts with Group By / color encoding**: legends are placed outside the axes at `bbox_to_anchor=(1.02, 1)` so they never overlap the plot area, regardless of the number of groups.
- **Scatter and histogram**: slightly larger defaults (`(11, 7)`) to give axis labels room.
- `ax.set_title` given `pad=12` for consistent spacing from the top of the axes.

### Complete filter values (`backend/profiler.py`, `frontend/app.py`)

Previously the **Build Your Own** filter multiselect only showed the top 5 categories for a column (the limit imposed by `value_counts().head(5)`). Now all unique values are surfaced:

- `ColumnProfile` gains a new `all_categories: list[str]` field — all unique string values for a categorical column, sorted alphabetically and capped at 500 entries.
- `to_dict()` includes `all_categories` so it flows through the `/upload` response to the frontend.
- `_profile_column` now computes `all_cats = sorted(str_series.unique().tolist())[:500]` alongside the existing `top_categories` (kept at top 5 for the schema panel and LLM context).
- `app.py` builds `col_categories` from `all_categories` first, falling back to `top_categories` keys for any profiles that pre-date this change. The filter multiselect now shows every unique value in the column.

---

## Checkpoint 14 — Streamlit Cloud Deployment & Backend Auto-Start
**Status:** Complete

### Problem
Streamlit Community Cloud only hosts the Streamlit frontend process — no separate FastAPI server is running. All `requests` calls to `BACKEND_URL` would fail immediately on Cloud while continuing to work fine locally (where the backend is started manually).

### Fix: dependency resolution (`requirements.txt`, `.python-version`)
Two issues blocked the initial Cloud deployment:
- `supabase==2.10.0` requires `httpx>=0.26,<0.28` but the file pinned `httpx==0.28.1` — resolved by downgrading to `httpx==0.27.2`.
- Streamlit Cloud defaulted to Python 3.14, which has no pre-built wheels for several pinned packages (`pandas`, `psycopg2-binary`, `kaleido`), causing source-builds that timed out. Fixed by adding `.python-version` containing `3.12`.

### Fix: backend auto-start (`frontend/app.py`)
Added `_ensure_backend()`, decorated with `@st.cache_resource`, that runs exactly once per Streamlit process lifetime:
1. Pings `GET /health` on `BACKEND_URL` (default `http://localhost:8000`) with a 3-second timeout.
2. If the backend responds, returns immediately (`"already_running"`).
3. If not, spawns `uvicorn backend.main:app --host 127.0.0.1 --port 8000` as a subprocess via `subprocess.Popen`, using `sys.executable` to ensure the same venv Python is used and `Path(__file__).parent.parent` as the working directory (repo root).
4. Polls `/health` every second for up to 30 seconds, returning `"started"` once the server responds.
5. A `show_spinner="Starting backend server…"` message is displayed in the UI during the wait.

`_ensure_backend()` is called immediately after `_init_state()` at app startup, before any user-facing UI is rendered.

### Behaviour by environment
| Environment | Backend already running | Result |
|---|---|---|
| Local dev (backend started separately) | Yes | Health check passes, no-op |
| Local dev (no backend started) | No | Auto-started, ready within ~5 s |
| Streamlit Community Cloud | No | Auto-started on first load, cached for all subsequent reruns |

### File changes
- `requirements.txt` — `httpx==0.28.1` → `httpx==0.27.2`
- `.python-version` — new file, pins deployment to Python `3.12`
- `frontend/app.py` — added `subprocess`, `sys`, `time`, `Path` imports; added `_ensure_backend()` with `@st.cache_resource`; called at startup

---

## Checkpoint 15 — In-Process Backend (No HTTP Server Required)
**Status:** Complete

### Problem
The Streamlit Cloud auto-start approach in Checkpoint 14 still relied on spawning a FastAPI subprocess and making HTTP calls to `localhost:8000`. On Streamlit Community Cloud this caused `Connection refused` errors on `/upload` and all other endpoints because the subprocess failed to bind reliably, and the export section still used the old `requests.get` pattern.

### Fix: direct in-process backend calls (`frontend/app.py`)
Removed the entire HTTP layer. All backend logic is now invoked directly as Python function calls:

- `_upload_file` — calls `ingest_upload()` and `profile_dataframe()` directly; stores the resulting DataFrame and metadata in `session_store` and returns a plain dict.
- `_call_suggest` — retrieves session data from `session_store` and calls `suggest_with_specs()` directly.
- `_render_confirmed` — retrieves the DataFrame from `session_store`, applies `convert_currency_cols`, constructs a `VizSpec`, calls `render_chart()` and `generate_insight()` directly, reads the PNG bytes from disk, and returns everything as a dict.
- `_submit_feedback` — calls the SQLAlchemy session directly (no-op when `DATABASE_URL` is unset).
- `_get_pdf_bytes` — new helper that converts PNG bytes to PDF in-memory using Matplotlib (replaces the old `GET /export/{id}` call).
- Export buttons now use `st.session_state.chart_bytes` directly for PNG and `_get_pdf_bytes()` for PDF, removing the last two `requests.get` calls that were missed in an earlier refactor.
- Removed `subprocess`, `time`, `requests` imports and the `BACKEND_URL` constant; removed `_ensure_backend()` and its call site.

### Fix: optional database (`backend/config.py`, `backend/database.py`)
`database_url` had no default, causing `pydantic-settings` to raise a `ValidationError` at startup when `DATABASE_URL` was not set. Fixed by:
- `config.py` — `database_url: str = ""` (empty string default).
- `database.py` — replaced module-level `create_engine()` call (which ran unconditionally at import time) with lazy `_get_engine()` / `_get_session_factory()` helpers that only create the engine when `database_url` is non-empty. `get_db()`, `init_db()`, and `check_connection()` all become safe no-ops when no database is configured.

### File changes
- `frontend/app.py` — removed HTTP-based helpers; added direct backend call helpers; added `_get_pdf_bytes()`; fixed export section; removed `_ensure_backend()`
- `backend/config.py` — `database_url` made optional (empty default)
- `backend/database.py` — lazy engine initialisation; all operations no-op without `DATABASE_URL`

---

## Checkpoint 16 — Streamlit Cloud Hosting Configuration
**Status:** Complete

### Problems resolved
Three separate issues prevented a clean Streamlit Cloud deployment after the in-process refactor:

1. **`ModuleNotFoundError: No module named 'backend'`** — Streamlit Cloud sets the working directory to the folder containing the main file (`frontend/`), so the `backend/` package one level up was not on `sys.path`.
2. **Secrets not visible to `pydantic-settings`** — Streamlit Cloud stores secrets in `st.secrets`; it does NOT automatically inject them into `os.environ`. `pydantic-settings` reads `os.environ`, so `ANTHROPIC_API_KEY` was never found and `Settings()` raised a `ValidationError`.
3. **Broken `requirements.txt`** — `kaleido==0.2.1` has no Python 3.12 pre-built wheel and would fail to install; `supabase==2.10.0` is not imported anywhere in the codebase; `pytest-asyncio==1.3.0` does not exist on PyPI; `pytest` and `pytest-asyncio` are dev-only and do not belong in the production requirements.

### Fix 1: `sys.path` (`frontend/app.py`)
Added at the very top of `app.py`, before any backend imports:
```python
sys.path.insert(0, str(Path(__file__).parent.parent))
```
`Path(__file__).parent.parent` resolves to the repo root regardless of the working directory, making `backend.*` importable on Cloud and in any local setup where the script is run from a non-root directory.

### Fix 2: Streamlit secrets bridge (`frontend/app.py`)
Added between `import streamlit as st` and the first `from backend.*` import (order matters — `backend/config.py` runs `Settings()` at import time):
```python
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str):
            os.environ.setdefault(_k.upper(), _v)
except Exception:
    pass  # no secrets.toml locally — .env is used instead
```
`os.environ.setdefault` ensures locally-set env vars and `.env` values are never overwritten.

### Fix 3: `requirements.txt` cleanup
- Removed `kaleido==0.2.1` — not used (app renders with Matplotlib, never calls `plotly_fig.write_image()`); no Python 3.12 wheel available.
- Removed `supabase==2.10.0` — package is not imported anywhere; SQLAlchemy + psycopg2 connect to Supabase directly.
- Removed `pytest==8.3.4` and `pytest-asyncio==1.3.0` — dev-only; `pytest-asyncio 1.3.0` does not exist on PyPI and would abort the Cloud install.
- Created `requirements-dev.txt` with `-r requirements.txt` plus `pytest==8.3.4` and `pytest-asyncio==0.23.8` (valid version).

### New files
- `.streamlit/config.toml` — sets `maxUploadSize = 200` and disables anonymous usage stats.
- `.streamlit/secrets.toml.example` — committed template listing every required and optional secret, with instructions for both local Streamlit dev (copy to `secrets.toml`) and the Streamlit Cloud dashboard.
- `requirements-dev.txt` — dev/test dependencies separated from the production install.

### `.gitignore` update
Added `.streamlit/secrets.toml` to prevent accidental commit of real API keys.

### Local development (summary)
```bash
# Option A — .env file (existing)
cp .env.example .env          # fill in ANTHROPIC_API_KEY
streamlit run frontend/app.py

# Option B — Streamlit secrets
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # fill in keys
streamlit run frontend/app.py
```

### Streamlit Cloud deployment (summary)
1. Push to GitHub.
2. In the app dashboard → **Settings → Secrets**, paste the contents of `.streamlit/secrets.toml.example` with real values.
3. Set **Main file path** to `frontend/app.py`.
4. Deploy — no backend server subprocess needed.

---

## Checkpoint 17 — AI Layer Input & Output Guardrails
**Status:** Complete

### Problem
The AI layer accepted raw user prompt strings with no validation before forwarding them to Claude. A malicious user could:
- Attempt **prompt injection** to override the system prompt ("ignore previous instructions", "jailbreak", DAN mode, etc.)
- Try to **extract secrets** by asking for the API key, database password, `.env` contents, or credentials
- Use **social engineering** techniques such as role-play, fictional scenarios, or instruction markers (`[INST]`, `<system>`) to bypass AI safety guidelines
- Submit **homoglyph / Unicode-obfuscated** variants of the above to defeat naive string matching

### Fix: `backend/guardrails.py` (new file)

A standalone guardrails module with two layers of protection:

**Input guardrails — `validate_input(prompt)`**

Runs four checks in priority order. Raises `GuardrailViolation` (a `ValueError` subclass carrying a `category` field) on the first failure:

| Category | Patterns detected |
|---|---|
| `length` | Prompts longer than 2 000 characters |
| `injection` | "ignore previous instructions", "forget directives", "disregard", "override system", "you are now", "new instructions", "jailbreak", "DAN mode", "do anything now", "no restrictions", "print/reveal system prompt", "what are your instructions" |
| `secret_extraction` | "api key", "secret key", "access key", "Anthropic … key/token", "password", "passphrase", "credentials", "private key", "environment variables", `.env`, `ANTHROPIC_API_KEY`, "database password/url", "print/reveal … key/token/secret", "exfiltrate" |
| `social_engineering` | "pretend you are", "act as if", "role-play", "for educational purposes … show/reveal", "hypothetically … what/tell", "in a fictional scenario", "without restrictions", "completely unrestricted", `<system>` tags, `[INST]`/`[/INST]` markers |

All checks normalize text with **NFKC Unicode normalization** before pattern matching to defeat full-width character and homoglyph obfuscation.

**Output guardrails**

Applied to every Claude response before it reaches the user:

- `sanitize_insight(text)` — strips control characters, redacts `sk-ant-*` Anthropic keys, OpenAI-style `sk-*` keys, base64 tokens with `=` padding, and database connection strings (Postgres, MySQL, MongoDB, Redis, SQLite); caps output at 1 500 characters.
- `sanitize_title(title)` — NFKC-normalizes, strips control characters, caps at 200 characters.
- `validate_viz_spec_output(raw)` — scans all text fields in the parsed VizSpec JSON (`title`, `interpreted_intent`, `x_axis`, `y_axis`, `alignment_issues`) for potential secrets; returns a list of warning strings without raising.

### Integration: `backend/ai_layer.py`

- `interpret_prompt()` — calls `validate_input(prompt_text)` **before** the Claude API call; applies `sanitize_title()` to the returned chart title and `validate_viz_spec_output()` to the full parsed JSON.
- `generate_insight()` — passes the raw Claude response through `sanitize_insight()` before returning.

### Integration: `backend/main.py`

All three prompt-accepting endpoints validate user input **before any database writes**, returning HTTP 422 on a `GuardrailViolation`:

- `POST /prompt` — `validate_input()` called before the `DBPromptRequest` row is created; `GuardrailViolation` also caught inside the render try-block and returned as 422 rather than 500.
- `POST /interpret` — `validate_input()` called before session lookup.
- `POST /render` — `validate_input()` called before session lookup.

### Tests: `tests/test_guardrails.py` (new file)

49 tests covering all guardrail surfaces:

- Length limits (at-limit passes, over-limit blocked)
- Injection pattern detection (12 attack variants)
- Secret extraction detection (9 attack variants)
- Social engineering detection (9 attack variants + fictional-scenario overlap case)
- Unicode / homoglyph obfuscation (full-width chars, zero-width joiners)
- Output insight sanitization (clean pass-through, control-char stripping, Anthropic key redaction, DB URL redaction, length truncation)
- Title sanitization (normal pass-through, length cap, control-char stripping)
- VizSpec output validation (clean spec, key-in-title flagged)

### File changes
- `backend/guardrails.py` — new; all guardrail logic
- `backend/ai_layer.py` — imports and integrates `validate_input`, `sanitize_insight`, `sanitize_title`, `validate_viz_spec_output`
- `backend/main.py` — imports `GuardrailViolation`, `validate_input`; adds boundary checks to `/prompt`, `/interpret`, `/render`
- `tests/test_guardrails.py` — new; 49 passing tests

---

## Checkpoint 18 — Supabase Scoped to Feedback Only
**Status:** Complete

### Problem
The original data model had Supabase (via SQLAlchemy) recording seven entity types: User, Dataset, DataColumnMetadata, PromptRequest, VisualizationSpec, GeneratedOutput, and Feedback. After the in-process refactor (Checkpoint 15), the frontend bypassed all FastAPI endpoints and called backend functions directly — meaning none of the DB writes actually executed in the real app. The only DB write that was attempted was in `_submit_feedback`, but it depended on a User row and a GeneratedOutput FK that were never written, so it silently failed.

### Fix: single standalone Feedback table

Supabase is now used exclusively to collect star-rating feedback from users. All other DB models and writes have been removed.

**`backend/models.py`** — Replaced all 7 ORM models with a single standalone `Feedback` table (no foreign keys to any other table):

| Column | Type | Notes |
|---|---|---|
| `feedback_id` | UUID (PK) | Auto-generated |
| `output_id` | UUID | Local chart identifier — no FK |
| `session_id` | String | Session that produced the chart |
| `rating` | Integer (1–5) | Star rating |
| `comments` | Text | Optional free-text comment |
| `revision_requested` | Boolean | Whether the user asked for a revision |
| `chart_type` | String | bar / line / scatter / pie / histogram |
| `chart_title` | String | Title of the rated chart |
| `submitted_at` | Timestamp | Auto-set on insert |

**`backend/main.py`** — Major cleanup:
- Removed imports: `User`, `Dataset`, `DataColumnMetadata`, `PromptRequest`, `VisualizationSpec`, `GeneratedOutput`
- Removed `_get_or_create_system_user` helper
- Removed `db: Session = Depends(get_db)` from `/upload`, `/render`, `/suggest`, `/auto-preview`, `/prompt` — none of these endpoints write to the DB anymore
- Removed `/chart/{output_id}` and `/export/{output_id}` endpoints (both depended on `GeneratedOutput`)
- Simplified `/feedback` endpoint — writes directly to the standalone `Feedback` table; no FK lookups required
- Added `session_id`, `chart_type`, `chart_title` to `FeedbackBody`
- `output_id` in all render responses is now a locally generated `uuid.uuid4()`

**`frontend/app.py`** — `_submit_feedback` rewritten:
- Removed `User` query (no User table)
- Reads `chart_type` and `chart_title` from `st.session_state.viz_spec` and writes them into the `Feedback` row
- Remains a silent no-op when `DATABASE_URL` is not configured

**`backend/config.py`** — Removed unused `supabase_url` and `supabase_anon_key` fields. Only `database_url` is needed (SQLAlchemy connects directly via the Postgres connection string).

### Result
- `init_db()` now creates exactly one table: `feedbacks`
- Every star rating submitted in the UI is persisted to Supabase with chart context (type, title, session)
- No other operations touch the database
- Supabase remains fully optional — omit `DATABASE_URL` and feedback silently succeeds without persisting

### File changes
- `backend/models.py` — replaced 7 models with standalone `Feedback`
- `backend/main.py` — stripped DB writes from all non-feedback endpoints; simplified `/feedback`; removed `/chart` and `/export`
- `frontend/app.py` — fixed `_submit_feedback` to write chart context; removed `User` dependency
- `backend/config.py` — removed `supabase_url`, `supabase_anon_key`

---

## Checkpoint 19 — Feedback Write Fix & Supabase Table Migration
**Status:** Complete

### Problem
After Checkpoint 18, user feedback was still not appearing in Supabase for two reasons:

1. **Old table schema still in Supabase.** The original `feedbacks` table had `output_id → generated_outputs` and `user_id → users` as NOT NULL foreign keys. SQLAlchemy's `create_all` only creates missing tables — it does not alter existing ones. The new `_submit_feedback` write omitted both FK columns, causing a constraint violation that was silently swallowed.

2. **`_submit_feedback` swallowed all exceptions with bare `except Exception: pass`.** Any DB error (FK violation, connection failure, schema mismatch) was caught and discarded, making the failure completely invisible.

### Fix 1: surface errors in `_submit_feedback` (`frontend/app.py`)

Rewrote the exception handling:
- Removed the bare `except Exception: pass` wrapper
- Added `db.rollback()` on failure to keep the session clean
- Added `db.close()` in a `finally` block to prevent session leaks
- Surfaces the error to the user via `st.warning(f"Feedback could not be saved: {exc}")` so failures are visible

### Fix 2: Supabase table migration (manual SQL)

The `feedbacks` table in Supabase had to be recreated with the new standalone schema. Run in the Supabase SQL editor:

```sql
DROP TABLE IF EXISTS feedbacks CASCADE;

CREATE TABLE feedbacks (
    feedback_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    output_id          UUID NOT NULL,
    session_id         TEXT,
    rating             INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comments           TEXT,
    revision_requested BOOLEAN DEFAULT FALSE,
    chart_type         TEXT,
    chart_title        TEXT,
    submitted_at       TIMESTAMPTZ DEFAULT NOW()
);
```

### Fix 3: README data model updated

Replaced the 7-entity data model in `README.md` with the single `Feedback` table. Removed all FK-dependent entities that are no longer persisted.

### File changes
- `frontend/app.py` — `_submit_feedback` error handling rewritten; session properly closed in `finally`
- `README.md` — data model section replaced with single Feedback table
