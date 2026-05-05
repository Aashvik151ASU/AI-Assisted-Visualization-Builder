"""
Streamlit frontend — AI-Assisted Visualization Builder
AI suggests charts from schema/sample data; all rendering uses the full uploaded dataset.
"""
from __future__ import annotations

import os
from typing import Any

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(
    page_title="AI Visualization Builder",
    page_icon="📊",
    layout="wide",
)


# ── Session-state keys ─────────────────────────────────────────────────────────

def _init_state() -> None:
    defaults: dict[str, Any] = {
        "session_id": None,
        "dataset_id": None,
        "file_name": None,
        "row_count": None,
        "column_count": None,
        "validation_report": None,
        "schema_profile": None,
        "output_id": None,
        "chart_bytes": None,
        "insight": None,
        "viz_spec": None,
        "alignment_issues": [],
        "feedback_submitted": False,
        "ai_suggestions": [],
        "ai_suggestions_loaded": False,
        "currency_cols": [],
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


_init_state()


# ── Currency detection ─────────────────────────────────────────────────────────

_CURRENCY_SYMBOLS = frozenset("$€£¥₹₩₺₽")

def _detect_currency_cols(schema_profile: dict) -> list[str]:
    """Return column names whose sample values contain at least one currency symbol."""
    detected = []
    for col in (schema_profile or {}).get("columns", []):
        samples = col.get("sample_values", [])
        if any(sym in str(v) for v in samples for sym in _CURRENCY_SYMBOLS):
            detected.append(col["column_name"])
    return detected


# ── Helpers: API calls ─────────────────────────────────────────────────────────

def _upload_file(file_obj) -> dict[str, Any] | None:
    try:
        resp = requests.post(
            f"{BACKEND_URL}/upload",
            files={"file": (file_obj.name, file_obj.getvalue(), file_obj.type)},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as exc:
        detail = exc.response.json().get("detail", str(exc)) if exc.response is not None else str(exc)
        st.error(f"Upload failed: {detail}")
    except requests.RequestException as exc:
        st.error(f"Could not reach backend: {exc}")
    return None


def _call_suggest(session_id: str) -> list[dict] | None:
    try:
        resp = requests.post(
            f"{BACKEND_URL}/suggest",
            json={"session_id": session_id},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json().get("suggestions", [])
    except requests.HTTPError as exc:
        detail = exc.response.json().get("detail", str(exc)) if exc.response is not None else str(exc)
        st.error(f"Suggestions failed: {detail}")
    except requests.RequestException as exc:
        st.error(f"Could not reach backend: {exc}")
    return None


def _render_confirmed(
    session_id: str,
    prompt: str,
    spec: dict[str, Any],
    currency_cols: list[str] | None = None,
) -> dict[str, Any] | None:
    payload = {
        "session_id": session_id,
        "prompt": prompt,
        "chart_type": spec["chart_type"],
        "x_axis": spec["x_axis"],
        "y_axis": spec["y_axis"],
        "aggregation": spec["aggregation"],
        "agg_axis": spec.get("agg_axis", "y"),
        "title": spec.get("title", ""),
        "filters": spec.get("filters") or {},
        "grouping": spec.get("grouping"),
        "color_encoding": spec.get("color_encoding"),
        "interpreted_intent": spec.get("interpreted_intent", ""),
        "currency_cols": currency_cols or [],
    }
    try:
        resp = requests.post(f"{BACKEND_URL}/render", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as exc:
        detail = exc.response.json().get("detail", str(exc)) if exc.response is not None else str(exc)
        st.error(f"Chart rendering failed: {detail}")
    except requests.RequestException as exc:
        st.error(f"Could not reach backend: {exc}")
    return None


def _interpret_prompt(session_id: str, prompt: str) -> dict[str, Any] | None:
    try:
        resp = requests.post(
            f"{BACKEND_URL}/interpret",
            json={"session_id": session_id, "prompt": prompt},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as exc:
        detail = exc.response.json().get("detail", str(exc)) if exc.response is not None else str(exc)
        st.error(f"Interpretation failed: {detail}")
    except requests.RequestException as exc:
        st.error(f"Could not reach backend: {exc}")
    return None


def _fetch_chart(output_id: str) -> bytes | None:
    try:
        resp = requests.get(f"{BACKEND_URL}/chart/{output_id}", timeout=30)
        resp.raise_for_status()
        return resp.content
    except requests.RequestException:
        return None


def _submit_feedback(output_id: str, rating: int, comments: str, revision: bool) -> bool:
    try:
        resp = requests.post(
            f"{BACKEND_URL}/feedback",
            json={
                "output_id": output_id,
                "rating": rating,
                "comments": comments or None,
                "revision_requested": revision,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        st.error(f"Feedback submission failed: {exc}")
        return False


def _export_url(output_id: str, fmt: str) -> str:
    return f"{BACKEND_URL}/export/{output_id}?format={fmt}"


def _apply_chart_result(result: dict[str, Any]) -> None:
    """Write a render response into session state and trigger rerun."""
    st.session_state.output_id = result["output_id"]
    st.session_state.chart_bytes = _fetch_chart(result["output_id"])
    st.session_state.insight = result["insight"]
    st.session_state.viz_spec = result["viz_spec"]
    st.session_state.alignment_issues = result.get("alignment_issues", [])
    st.session_state.feedback_submitted = False
    st.rerun()


# ── UI helpers ─────────────────────────────────────────────────────────────────

def _render_validation_report(report: dict[str, Any]) -> None:
    passed = report.get("passed", True)
    st.markdown(f"**Validation:** {'✅ Passed' if passed else '❌ Failed'}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Rows", report.get("row_count", "—"))
    col2.metric("Columns", report.get("column_count", "—"))
    col3.metric("Duplicate rows", report.get("duplicate_count", 0))

    issues = report.get("issues", [])
    warnings = report.get("warnings", [])

    if issues:
        with st.expander(f"🔴 Errors ({len(issues)})", expanded=True):
            for issue in issues:
                st.error(f"**{issue['column']}**: {issue['message']}")

    if warnings:
        with st.expander(f"🟡 Warnings ({len(warnings)})"):
            for w in warnings:
                st.warning(f"**{w['column']}**: {w['message']}")

    null_pcts = report.get("null_percentages", {})
    if null_pcts:
        with st.expander("Null % per column"):
            for col, pct in null_pcts.items():
                st.markdown(
                    f"`{col}` — **{pct}%** "
                    f"{'🔴' if pct >= 50 else ('🟡' if pct > 0 else '🟢')}"
                )


def _render_schema_panel(profile: dict[str, Any]) -> None:
    columns = profile.get("columns", [])
    if not columns:
        return

    TYPE_ICONS = {
        "numeric": "🔢",
        "categorical": "🏷️",
        "datetime": "📅",
        "boolean": "☑️",
    }

    for col in columns:
        dtype = col.get("detected_type", "unknown")
        icon = TYPE_ICONS.get(dtype, "❓")
        with st.expander(f"{icon} {col['column_name']} — {dtype}"):
            meta_col1, meta_col2 = st.columns(2)
            meta_col1.write(f"**Null %:** {col.get('null_percentage', 0)}%")
            meta_col1.write(f"**Unique values:** {col.get('unique_count', '—')}")

            if dtype == "numeric":
                meta_col2.write(f"**Min:** {col.get('min_value', '—')}")
                meta_col2.write(f"**Max:** {col.get('max_value', '—')}")
                meta_col2.write(f"**Mean:** {col.get('mean', '—')}")
                meta_col2.write(f"**Std dev:** {col.get('std_dev', '—')}")

            if dtype == "categorical":
                top = col.get("top_categories", {})
                if top:
                    st.write("**Top categories:**")
                    for cat, count in top.items():
                        st.write(f"  - `{cat}` ({count})")

            samples = col.get("sample_values", [])
            if samples:
                st.write(f"**Samples:** {', '.join(str(s) for s in samples)}")


# ═══════════════════════════════════════════════════════════════════════════════
# Main UI
# ═══════════════════════════════════════════════════════════════════════════════

st.title("📊 AI-Assisted Visualization Builder")
st.caption(
    "Upload a dataset — let AI suggest charts from your schema, "
    "or build your own. Every chart renders against your full dataset."
)

# ── Step 1: File Upload ────────────────────────────────────────────────────────

st.header("1. Upload Dataset")
uploaded = st.file_uploader(
    "Choose a file (CSV, XLSX, JSON, Parquet)",
    type=["csv", "xlsx", "json", "parquet"],
    key="file_uploader",
)

if uploaded is not None:
    new_file = uploaded.name != st.session_state.get("file_name")

    if new_file:
        with st.spinner(f"Uploading and validating **{uploaded.name}**…"):
            result = _upload_file(uploaded)

        if result:
            st.session_state.session_id = result["session_id"]
            st.session_state.dataset_id = result["dataset_id"]
            st.session_state.file_name = result["file_name"]
            st.session_state.row_count = result["row_count"]
            st.session_state.column_count = result["column_count"]
            st.session_state.validation_report = result["validation_report"]
            st.session_state.schema_profile = result["schema_profile"]
            # Reset chart and suggestion state
            for key in ("output_id", "chart_bytes", "insight", "viz_spec"):
                st.session_state[key] = None
            st.session_state.alignment_issues = []
            st.session_state.feedback_submitted = False
            st.session_state.ai_suggestions = []
            st.session_state.ai_suggestions_loaded = False
            st.session_state.currency_cols = _detect_currency_cols(result["schema_profile"])
            st.success(
                f"Uploaded **{result['file_name']}** — "
                f"{result['row_count']:,} rows × {result['column_count']} columns"
            )

# ── Validation Report + Schema ─────────────────────────────────────────────────

if st.session_state.session_id:
    st.divider()
    left_col, right_col = st.columns([3, 2])

    with left_col:
        st.subheader("Validation Report")
        _render_validation_report(st.session_state.validation_report)

    with right_col:
        st.subheader("Schema Metadata")
        _render_schema_panel(st.session_state.schema_profile)

    # ── Constants ──────────────────────────────────────────────────────────────

    col_names = [
        c["column_name"]
        for c in (st.session_state.schema_profile or {}).get("columns", [])
    ]

    CHART_OPTIONS    = ["bar", "line", "scatter", "pie", "histogram"]
    AGG_OPTIONS      = ["sum", "mean", "count", "max", "min", "none"]
    AGG_AXIS_OPTIONS = ["Y-axis", "X-axis"]
    CHART_ICONS      = {"bar": "📊", "line": "📈", "scatter": "🔵", "pie": "🥧", "histogram": "📉"}

    # ── Amount / Currency Column Conversion ────────────────────────────────────

    st.divider()
    _auto_detected = _detect_currency_cols(st.session_state.schema_profile)
    _expander_label = (
        f"💱 Amount / Currency Columns — {len(_auto_detected)} auto-detected"
        if _auto_detected
        else "💱 Amount / Currency Columns"
    )
    with st.expander(_expander_label, expanded=bool(_auto_detected)):
        st.caption(
            "Select columns that hold amounts as currency strings — e.g. `$1,234.56`, "
            "`€9,999`. The app will strip the symbol and commas and convert to a number "
            "before every chart render. Auto-detected columns are pre-selected."
        )
        # key ties the widget directly to st.session_state.currency_cols
        st.multiselect(
            "Convert to numeric",
            options=col_names,
            default=[c for c in st.session_state.currency_cols if c in col_names],
            key="currency_cols",
            help="Supports: $ € £ ¥ ₹ ₩ ₺ ₽  and thousands commas",
        )
        if st.session_state.currency_cols:
            st.success(
                "Will convert: "
                + ", ".join(f"`{c}`" for c in st.session_state.currency_cols)
            )

    # ── Step 2: Visualize ──────────────────────────────────────────────────────

    st.divider()
    st.header("2. Visualize Your Data")

    tab_ai, tab_manual = st.tabs(["🤖 AI Suggestions", "🛠️ Build Your Own"])

    # ── Tab 1 — AI Suggestions ─────────────────────────────────────────────────

    with tab_ai:
        st.caption(
            "AI reads your dataset's **schema and sample values** to suggest the most "
            "insightful charts. Click **Use This Chart** to render it instantly against "
            "your **full uploaded dataset**."
        )

        if not st.session_state.ai_suggestions_loaded:
            if st.button("Get AI Suggestions", type="primary", key="btn_get_suggestions"):
                with st.spinner("AI is analysing your dataset schema and samples…"):
                    suggestions = _call_suggest(st.session_state.session_id)
                if suggestions is not None:
                    st.session_state.ai_suggestions = suggestions
                    st.session_state.ai_suggestions_loaded = True
                    st.rerun()
        else:
            if st.button("Refresh Suggestions", key="btn_refresh_suggestions"):
                st.session_state.ai_suggestions_loaded = False
                st.session_state.ai_suggestions = []
                st.rerun()

        if st.session_state.ai_suggestions_loaded and not st.session_state.ai_suggestions:
            st.warning("No suggestions could be generated for this dataset.")

        if st.session_state.ai_suggestions:
            n_cols = min(3, len(st.session_state.ai_suggestions))
            grid = st.columns(n_cols)
            for i, s in enumerate(st.session_state.ai_suggestions):
                with grid[i % n_cols]:
                    icon = CHART_ICONS.get(s["chart_type"], "📊")
                    st.markdown(f"**{icon} {s['title']}**")
                    st.caption(s["suggestion"])
                    st.markdown(
                        f"`{s['chart_type'].upper()}` &nbsp;·&nbsp; "
                        f"X: `{s['x_axis']}` &nbsp;·&nbsp; "
                        f"Y: `{s['y_axis']}` &nbsp;·&nbsp; "
                        f"Agg: `{s['aggregation']}`"
                    )
                    if st.button(
                        "Use This Chart", key=f"use_suggestion_{i}",
                        type="primary", use_container_width=True,
                    ):
                        with st.spinner(f"Rendering **{s['title']}** on your full dataset…"):
                            result = _render_confirmed(
                                st.session_state.session_id,
                                s["suggestion"],
                                {
                                    "chart_type": s["chart_type"],
                                    "x_axis": s["x_axis"],
                                    "y_axis": s["y_axis"],
                                    "aggregation": s["aggregation"],
                                    "agg_axis": "y",
                                    "title": s["title"],
                                    "filters": s.get("filters") or {},
                                    "grouping": s.get("grouping"),
                                    "color_encoding": s.get("color_encoding"),
                                    "interpreted_intent": s["suggestion"],
                                },
                                currency_cols=st.session_state.currency_cols,
                            )
                        if result:
                            _apply_chart_result(result)

    # ── Tab 2 — Build Your Own ─────────────────────────────────────────────────

    with tab_manual:
        st.caption(
            "Choose every parameter yourself — chart type, columns, aggregation, "
            "group-by, and filters. Renders against your **full dataset**."
        )

        # Build a lookup of column type and known categorical values from schema
        _schema_cols = (st.session_state.schema_profile or {}).get("columns", [])
        col_types = {c["column_name"]: c["detected_type"] for c in _schema_cols}
        col_categories = {
            c["column_name"]: (
                c["all_categories"]
                if c.get("all_categories")
                else list(c.get("top_categories", {}).keys())
            )
            for c in _schema_cols
            if c.get("all_categories") or c.get("top_categories")
        }

        # Row 1 — chart type + aggregation
        mc1, mc2 = st.columns(2)
        with mc1:
            manual_chart = st.selectbox("Chart Type", CHART_OPTIONS, key="manual_chart_type")
        with mc2:
            manual_agg = st.selectbox(
                "Aggregation Function",
                AGG_OPTIONS,
                key="manual_agg",
                help="sum=total  |  mean=average  |  count=# of rows  |  none=raw values",
            )

        # Row 2 — axis columns
        md1, md2 = st.columns(2)
        with md1:
            manual_x = st.selectbox("X-axis column", col_names, key="manual_x")
        with md2:
            manual_y = st.selectbox(
                "Y-axis column",
                col_names,
                index=min(1, len(col_names) - 1) if col_names else 0,
                key="manual_y",
            )

        # Row 3 — aggregation axis + group by
        ma1, ma2 = st.columns(2)
        with ma1:
            manual_agg_axis_label = st.selectbox(
                "Apply aggregation to",
                AGG_AXIS_OPTIONS,
                key="manual_agg_axis",
                help=(
                    "Y-axis (standard): group by X column, aggregate Y values.\n"
                    "X-axis: group by Y column, aggregate X values."
                ),
            )
            manual_agg_axis = "y" if manual_agg_axis_label == "Y-axis" else "x"
        with ma2:
            groupby_options = ["— none —"] + col_names
            manual_groupby = st.selectbox(
                "Group By (split series)",
                groupby_options,
                key="manual_groupby",
                help="Split the chart into separate series/colours by this column.",
            )
            manual_groupby_val = None if manual_groupby == "— none —" else manual_groupby

        # Row 4 — chart title
        manual_title = st.text_input(
            "Chart Title (optional)",
            key="manual_title",
            placeholder="Leave blank to auto-generate",
        )

        # Filters expander
        with st.expander("Filters (optional — narrow data before rendering)"):
            st.caption(
                "Each row restricts the dataset to rows matching that column's value(s). "
                "Categorical columns offer a multi-select; others accept a typed value."
            )
            _NO_COL = "— none —"
            manual_filters: dict[str, Any] = {}
            for fi in range(3):
                fc, fv = st.columns([2, 3])
                with fc:
                    f_col = st.selectbox(
                        f"Filter column {fi + 1}",
                        [_NO_COL] + col_names,
                        key=f"filter_col_{fi}",
                        label_visibility="collapsed" if fi > 0 else "visible",
                    )
                with fv:
                    if f_col == _NO_COL:
                        st.text_input(
                            "Value",
                            value="",
                            key=f"filter_val_{fi}",
                            disabled=True,
                            label_visibility="collapsed" if fi > 0 else "visible",
                        )
                    elif col_types.get(f_col) == "categorical" and f_col in col_categories:
                        chosen = st.multiselect(
                            "Values",
                            col_categories[f_col],
                            key=f"filter_val_{fi}",
                            label_visibility="collapsed" if fi > 0 else "visible",
                        )
                        if chosen:
                            manual_filters[f_col] = chosen
                    else:
                        typed = st.text_input(
                            "Value",
                            key=f"filter_val_{fi}",
                            placeholder="e.g. North",
                            label_visibility="collapsed" if fi > 0 else "visible",
                        )
                        if typed.strip():
                            manual_filters[f_col] = typed.strip()

            if manual_filters:
                st.info(
                    "Active: "
                    + "  |  ".join(
                        f"`{c}` ∈ {v}" if isinstance(v, list) else f"`{c}` = `{v}`"
                        for c, v in manual_filters.items()
                    )
                )

        if st.button(
            "Generate Chart", type="primary", key="manual_generate",
            disabled=not col_names,
        ):
            agg_col   = manual_y if manual_agg_axis == "y" else manual_x
            group_col = manual_x if manual_agg_axis == "y" else manual_y
            title = manual_title.strip() or f"{manual_agg.title()} of {agg_col} by {group_col}"
            with st.spinner("Rendering chart on your full dataset…"):
                result = _render_confirmed(
                    st.session_state.session_id,
                    f"{manual_chart} of {manual_y} by {manual_x}",
                    {
                        "chart_type": manual_chart,
                        "x_axis": manual_x,
                        "y_axis": manual_y,
                        "aggregation": manual_agg,
                        "agg_axis": manual_agg_axis,
                        "title": title,
                        "filters": manual_filters,
                        "grouping": manual_groupby_val,
                        "color_encoding": None,
                        "interpreted_intent": f"User-defined {manual_chart} chart",
                    },
                    currency_cols=st.session_state.currency_cols,
                )
            if result:
                _apply_chart_result(result)

    # ── Step 3: Chart + Insight ────────────────────────────────────────────────

    if st.session_state.chart_bytes:
        st.divider()
        st.header("3. Your Chart")

        if st.session_state.alignment_issues:
            with st.expander("⚠️ Alignment issues detected"):
                for issue in st.session_state.alignment_issues:
                    st.warning(issue)

        st.image(st.session_state.chart_bytes, use_container_width=True)

        viz = st.session_state.viz_spec or {}
        if viz:
            with st.expander("Chart specification"):
                spec_c1, spec_c2, spec_c3 = st.columns(3)
                spec_c1.write(f"**Type:** {viz.get('chart_type', '—')}")
                spec_c1.write(f"**X-axis:** {viz.get('x_axis', '—')}")
                spec_c2.write(f"**Y-axis:** {viz.get('y_axis', '—')}")
                spec_c2.write(f"**Aggregation:** {viz.get('aggregation', '—')}")
                agg_axis_val = viz.get("agg_axis", "y")
                spec_c3.write(
                    f"**Aggregation on:** {'Y-axis' if agg_axis_val == 'y' else 'X-axis'}"
                )
                if viz.get("grouping"):
                    spec_c3.write(f"**Group by:** {viz['grouping']}")
                if viz.get("filters"):
                    for fc, fv in viz["filters"].items():
                        disp = ", ".join(fv) if isinstance(fv, list) else fv
                        spec_c3.write(f"**Filter:** `{fc}` = {disp}")

        st.subheader("💡 Insight")
        st.info(st.session_state.insight)

        # ── Export ─────────────────────────────────────────────────────────────

        st.subheader("Export")
        exp_col1, exp_col2 = st.columns(2)

        with exp_col1:
            png_resp = requests.get(
                _export_url(st.session_state.output_id, "png"), timeout=15
            )
            if png_resp.ok:
                st.download_button(
                    label="⬇️ Download PNG",
                    data=png_resp.content,
                    file_name=f"chart_{st.session_state.output_id[:8]}.png",
                    mime="image/png",
                )

        with exp_col2:
            pdf_resp = requests.get(
                _export_url(st.session_state.output_id, "pdf"), timeout=30
            )
            if pdf_resp.ok:
                st.download_button(
                    label="⬇️ Download PDF",
                    data=pdf_resp.content,
                    file_name=f"chart_{st.session_state.output_id[:8]}.pdf",
                    mime="application/pdf",
                )

        # ── Feedback ───────────────────────────────────────────────────────────

        st.divider()
        st.header("4. Feedback")

        if st.session_state.feedback_submitted:
            st.success("Thanks for your feedback!")
        else:
            fb_col1, fb_col2 = st.columns([1, 2])

            with fb_col1:
                rating = st.radio(
                    "Rate this chart",
                    options=[1, 2, 3, 4, 5],
                    format_func=lambda x: "⭐" * x,
                    horizontal=True,
                    index=4,
                    key="fb_rating",
                )

            with fb_col2:
                comments = st.text_area("Comments (optional)", height=70, key="fb_comments")
                revision = st.checkbox("Request a revision", key="fb_revision")

            if st.button("Submit Feedback"):
                ok = _submit_feedback(
                    st.session_state.output_id, rating, comments, revision
                )
                if ok:
                    st.session_state.feedback_submitted = True
                    st.rerun()
