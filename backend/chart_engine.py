from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from backend.ai_layer import VizSpec
from backend.config import settings

_AGG_FUNCS = {"sum": "sum", "mean": "mean", "max": "max", "min": "min"}

# Matches any currency symbol, thousands comma, or surrounding whitespace
_CURRENCY_CHARS = re.compile(r"[$€£¥₹₩₺₽,\s]")


def convert_currency_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """
    Strip currency symbols, commas, and whitespace from the given columns
    and coerce each to float.  Non-parseable values become NaN.
    """
    if not cols:
        return df
    df = df.copy()
    for col in cols:
        if col not in df.columns:
            continue
        df[col] = (
            df[col]
            .astype(str)
            .str.replace(_CURRENCY_CHARS, "", regex=True)
            .str.strip()
            .replace("", float("nan"))
            .astype(float)
        )
    return df


# ── Return type ────────────────────────────────────────────────────────────────

@dataclass
class ChartResult:
    output_path: str
    chart_type: str
    stats: dict[str, Any] = field(default_factory=dict)


# ── Public entry point ─────────────────────────────────────────────────────────

def render_chart(
    df: pd.DataFrame,
    spec: VizSpec,
    output_dir: str | None = None,
    backend: Literal["plotly", "matplotlib"] = "matplotlib",
) -> ChartResult:
    """
    Apply filters and aggregation from spec, render a chart, and save as PNG.

    backend="matplotlib" — Matplotlib static rendering (default)
    backend="plotly"     — Plotly Express via kaleido (requires kaleido package)
    """
    out_dir = Path(output_dir or settings.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = _apply_filters(df, spec.filters)

    if df.empty:
        raise ValueError("No data remains after applying filters.")

    plot_df, eff_x, eff_y = _apply_aggregation(df, spec)

    filename = f"{spec.chart_type}_{uuid.uuid4().hex[:8]}.png"
    output_path = str(out_dir / filename)

    if backend == "matplotlib":
        mpl_fig = _render_figure_matplotlib(plot_df, spec, eff_x, eff_y)
        mpl_fig.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(mpl_fig)
    else:
        plotly_fig = _render_figure(plot_df, spec, eff_x, eff_y)
        plotly_fig.write_image(output_path)

    stats = _compute_stats(plot_df, spec, eff_x, eff_y)
    return ChartResult(output_path=output_path, chart_type=spec.chart_type, stats=stats)


# ── Filtering ──────────────────────────────────────────────────────────────────

def _apply_filters(df: pd.DataFrame, filters: dict[str, Any]) -> pd.DataFrame:
    for col, val in (filters or {}).items():
        if col not in df.columns:
            continue
        if isinstance(val, list):
            df = df[df[col].astype(str).isin([str(v) for v in val])]
        else:
            df = df[df[col].astype(str) == str(val)]
    return df.copy()


# ── Aggregation ────────────────────────────────────────────────────────────────

_MAX_RAW_BARS    = 100    # unique x values before forcing aggregation on bar/pie
_MAX_SCATTER_PTS = 50_000 # max individual points for scatter/line before sampling


def _apply_aggregation(df: pd.DataFrame, spec: VizSpec) -> tuple[pd.DataFrame, str, str]:
    """
    Return (plot_df, effective_x_col, effective_y_col).

    spec.agg_axis controls which axis gets the aggregation function applied:
      "y" (default) — group by X, aggregate Y  →  (x_col, agg(y_col))
      "x"           — group by Y, aggregate X  →  (y_col, agg(x_col))

    For histogram, raw x values are distributed — no aggregation needed.
    For aggregation="none", safety limits prevent illegible charts:
      - bar/pie with > _MAX_RAW_BARS unique category values → auto count
      - scatter/line with > _MAX_SCATTER_PTS rows → sample down
    """
    x = spec.x_axis
    y = spec.y_axis
    agg = spec.aggregation
    agg_axis = getattr(spec, "agg_axis", "y")

    if spec.chart_type == "histogram":
        return df, x, x

    # Determine which column is the grouping dimension and which is the measure
    if agg_axis == "x":
        group_col, agg_col = y, x
    else:
        group_col, agg_col = x, y

    if agg == "none":
        if spec.chart_type in ("bar", "pie"):
            n_unique = df[group_col].nunique() if group_col in df.columns else 0
            if n_unique > _MAX_RAW_BARS or len(df) > _MAX_RAW_BARS:
                group_cols = _group_cols(df, group_col, spec.grouping)
                result = df.groupby(group_cols).size().reset_index(name="count")
                return result, group_col, "count"
        elif spec.chart_type in ("scatter", "line") and len(df) > _MAX_SCATTER_PTS:
            return df.sample(n=_MAX_SCATTER_PTS, random_state=42).reset_index(drop=True), group_col, agg_col
        return df, group_col, agg_col

    # Normalise: if the agg column is literally "count" treat it as a count agg
    if agg_col == "count" and agg not in _AGG_FUNCS:
        agg = "count"

    group_cols = _group_cols(df, group_col, spec.grouping)

    if agg == "count":
        result = df.groupby(group_cols).size().reset_index(name="count")
        return result, group_col, "count"

    if agg in _AGG_FUNCS and agg_col in df.columns:
        result = df.groupby(group_cols)[agg_col].agg(_AGG_FUNCS[agg]).reset_index()
        return result, group_col, agg_col

    return df, group_col, agg_col


def _group_cols(df: pd.DataFrame, x: str, grouping: str | None) -> list[str]:
    cols = [x] if x in df.columns else []
    if grouping and grouping in df.columns and grouping != x:
        cols.append(grouping)
    return cols or [x]


# ── Rendering ──────────────────────────────────────────────────────────────────

def _render_figure(df: pd.DataFrame, spec: VizSpec, eff_x: str, eff_y: str) -> go.Figure:
    x = eff_x if eff_x in df.columns else df.columns[0]
    title = spec.title or f"{spec.chart_type.title()} Chart"
    color = spec.grouping if (spec.grouping and spec.grouping in df.columns) else None

    if spec.chart_type == "bar":
        fig = px.bar(df, x=x, y=eff_y, color=color, title=title)

    elif spec.chart_type == "line":
        fig = px.line(df, x=x, y=eff_y, color=color, title=title)

    elif spec.chart_type == "scatter":
        y_col = eff_y if eff_y in df.columns else df.columns[-1]
        fig = px.scatter(df, x=x, y=y_col, color=color, title=title)

    elif spec.chart_type == "pie":
        y_col = eff_y if eff_y in df.columns else None
        fig = px.pie(df, names=x, values=y_col, title=title)

    elif spec.chart_type == "histogram":
        fig = px.histogram(df, x=x, color=color, title=title)

    else:
        raise ValueError(f"Unsupported chart type: {spec.chart_type!r}")

    fig.update_layout(template="plotly_white")
    return fig


# ── Matplotlib rendering ───────────────────────────────────────────────────────

def _render_figure_matplotlib(df: pd.DataFrame, spec: VizSpec, eff_x: str, eff_y: str) -> plt.Figure:
    x = eff_x if eff_x in df.columns else df.columns[0]
    title = spec.title or f"{spec.chart_type.title()} Chart"
    color_col = spec.grouping if (spec.grouping and spec.grouping in df.columns) else None

    if spec.chart_type == "bar":
        n_bars = int(df[x].nunique()) if x in df.columns else len(df)
        fig_width = max(10, min(n_bars * 0.55, 36))
        fig, ax = plt.subplots(figsize=(fig_width, 7))
        if color_col:
            pivoted = df.pivot_table(index=x, columns=color_col, values=eff_y, aggfunc="sum")
            pivoted.plot(kind="bar", ax=ax)
            ax.set_xlabel(x)
            ax.set_ylabel(eff_y)
            ax.legend(
                title=color_col,
                bbox_to_anchor=(1.02, 1),
                loc="upper left",
                borderaxespad=0,
            )
        else:
            ax.bar(df[x].astype(str), df[eff_y])
            ax.set_xlabel(x)
            ax.set_ylabel(eff_y)
        rotation = 90 if n_bars > 20 else 45
        plt.xticks(rotation=rotation, ha="right")

    elif spec.chart_type == "line":
        fig, ax = plt.subplots(figsize=(13, 7))
        if color_col:
            for grp, sub in df.groupby(color_col):
                ax.plot(sub[x], sub[eff_y], label=str(grp))
            ax.legend(
                title=color_col,
                bbox_to_anchor=(1.02, 1),
                loc="upper left",
                borderaxespad=0,
            )
        else:
            ax.plot(df[x], df[eff_y])
        ax.set_xlabel(x)
        ax.set_ylabel(eff_y)

    elif spec.chart_type == "scatter":
        fig, ax = plt.subplots(figsize=(11, 7))
        y_col = eff_y if eff_y in df.columns else df.columns[-1]
        ax.scatter(df[x], df[y_col], alpha=0.6)
        ax.set_xlabel(x)
        ax.set_ylabel(y_col)

    elif spec.chart_type == "pie":
        n_slices = len(df)
        fig_width = 13 if n_slices > 10 else 10
        fig, ax = plt.subplots(figsize=(fig_width, 8))
        y_col = eff_y if eff_y in df.columns else None
        labels = df[x].astype(str).tolist()
        values = df[y_col].tolist() if y_col else [1] * len(df)
        if n_slices > 10:
            # Too many slices for readable inline labels — move to legend
            wedges, _, _ = ax.pie(values, autopct="%1.1f%%", labels=None, pctdistance=0.85)
            ax.legend(
                wedges,
                labels,
                title=x,
                loc="center left",
                bbox_to_anchor=(1.0, 0, 0.45, 1),
            )
        else:
            ax.pie(values, labels=labels, autopct="%1.1f%%")

    elif spec.chart_type == "histogram":
        fig, ax = plt.subplots(figsize=(11, 7))
        ax.hist(df[x].dropna(), bins="auto", edgecolor="white")
        ax.set_xlabel(x)
        ax.set_ylabel("Frequency")

    else:
        raise ValueError(f"Unsupported chart type: {spec.chart_type!r}")

    ax.set_title(title, pad=12)
    plt.tight_layout()
    return fig


# ── Stats ──────────────────────────────────────────────────────────────────────

def _compute_stats(df: pd.DataFrame, spec: "VizSpec", eff_x: str, eff_y: str) -> dict[str, Any]:
    stats: dict[str, Any] = {"row_count": len(df)}
    x_col = eff_x if eff_x in df.columns else None

    if eff_y in df.columns and pd.api.types.is_numeric_dtype(df[eff_y]):
        series = df[eff_y].dropna()
        stats["y_min"] = round(float(series.min()), 4)
        stats["y_max"] = round(float(series.max()), 4)
        stats["y_mean"] = round(float(series.mean()), 4)
        stats["y_sum"] = round(float(series.sum()), 4)

        if x_col and x_col in df.columns:
            ordered = df[[x_col, eff_y]].dropna().sort_values(eff_y, ascending=False)
            stats["highest"] = f"{ordered.iloc[0][x_col]} ({round(float(ordered.iloc[0][eff_y]), 2)})"
            stats["lowest"] = f"{ordered.iloc[-1][x_col]} ({round(float(ordered.iloc[-1][eff_y]), 2)})"
            stats["all_values"] = {
                str(row[x_col]): round(float(row[eff_y]), 2)
                for _, row in ordered.iterrows()
            }

        if spec.chart_type in ("line", "scatter") and x_col and x_col in df.columns:
            try:
                first = float(df[eff_y].iloc[0])
                last = float(df[eff_y].iloc[-1])
                stats["trend_direction"] = "upward" if last > first else ("downward" if last < first else "flat")
            except (ValueError, TypeError):
                pass

    return stats
