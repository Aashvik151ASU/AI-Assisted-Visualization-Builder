from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


# ── Column-level profile ───────────────────────────────────────────────────────

@dataclass
class ColumnProfile:
    column_name: str
    detected_type: str          # numeric | categorical | datetime | boolean
    null_percentage: float
    unique_count: int
    sample_values: list[Any]    # up to 5 representative values

    # numeric only
    min_value: float | None = None
    max_value: float | None = None
    mean: float | None = None
    median: float | None = None
    std_dev: float | None = None

    # categorical only
    top_categories: dict[str, int] = field(default_factory=dict)  # value → count (top 5)
    all_categories: list[str] = field(default_factory=list)       # all unique values (capped at 500)

    def to_dict(self) -> dict:
        return {
            "column_name":    self.column_name,
            "detected_type":  self.detected_type,
            "null_percentage": self.null_percentage,
            "unique_count":   self.unique_count,
            "sample_values":  self.sample_values,
            "min_value":      self.min_value,
            "max_value":      self.max_value,
            "mean":           self.mean,
            "median":         self.median,
            "std_dev":        self.std_dev,
            "top_categories": self.top_categories,
            "all_categories": self.all_categories,
        }


# ── Dataset-level profile ──────────────────────────────────────────────────────

@dataclass
class DatasetProfile:
    row_count: int
    column_count: int
    columns: list[ColumnProfile]

    def to_dict(self) -> dict:
        return {
            "row_count":    self.row_count,
            "column_count": self.column_count,
            "columns":      [c.to_dict() for c in self.columns],
        }

    def to_llm_context(self) -> str:
        """
        Compact plain-text summary sent to Claude as dataset context.
        Keeps token count low while giving the model enough info to
        recommend chart types, axes, and aggregations.
        """
        lines = [f"Dataset: {self.row_count} rows × {self.column_count} columns", "", "Columns:"]
        for col in self.columns:
            lines.append(_format_column_summary(col))
        return "\n".join(lines)


# ── Public entry point ─────────────────────────────────────────────────────────

def profile_dataframe(df: pd.DataFrame) -> DatasetProfile:
    """Generate a full profile for a cleaned DataFrame."""
    columns = [_profile_column(df[col]) for col in df.columns]
    return DatasetProfile(
        row_count=len(df),
        column_count=len(df.columns),
        columns=columns,
    )


# ── Per-column profiling ───────────────────────────────────────────────────────

def _profile_column(series: pd.Series) -> ColumnProfile:
    dtype = _detect_type(series)
    null_pct = round(series.isna().mean() * 100, 1)
    unique_count = int(series.nunique(dropna=True))
    sample = _sample_values(series)

    base = dict(
        column_name=series.name,
        detected_type=dtype,
        null_percentage=null_pct,
        unique_count=unique_count,
        sample_values=sample,
    )

    if dtype == "numeric":
        clean = series.dropna()
        return ColumnProfile(
            **base,
            min_value=_round(clean.min()),
            max_value=_round(clean.max()),
            mean=_round(clean.mean()),
            median=_round(clean.median()),
            std_dev=_round(clean.std()),
        )

    if dtype == "categorical":
        str_series = series.dropna().astype(str)
        top = str_series.value_counts().head(5).to_dict()
        all_cats = sorted(str_series.unique().tolist())[:500]
        return ColumnProfile(**base, top_categories=top, all_categories=all_cats)

    if dtype == "datetime":
        clean = series.dropna()
        return ColumnProfile(
            **base,
            min_value=str(clean.min().date()) if not clean.empty else None,
            max_value=str(clean.max().date()) if not clean.empty else None,
        )

    # boolean
    return ColumnProfile(**base)


def _detect_type(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    return "categorical"


def _sample_values(series: pd.Series, n: int = 5) -> list[Any]:
    values = series.dropna().unique()
    picked = values[:n]
    result = []
    for v in picked:
        if hasattr(v, "date"):
            result.append(str(v.date()))
        elif isinstance(v, (bool, np.bool_)):
            result.append(bool(v))
        elif isinstance(v, (int, np.integer)):
            result.append(int(v))
        elif isinstance(v, (float, np.floating)):
            result.append(round(float(v), 4))
        else:
            result.append(str(v) if not isinstance(v, str) else v)
    return result


def _round(value: Any, digits: int = 2) -> float | None:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


# ── LLM context formatting ─────────────────────────────────────────────────────

def _format_column_summary(col: ColumnProfile) -> str:
    null_str = f", {col.null_percentage}% null" if col.null_percentage > 0 else ", 0% null"

    if col.detected_type == "numeric":
        return (
            f"  - {col.column_name} (numeric): "
            f"range {col.min_value}–{col.max_value}, "
            f"mean {col.mean}, median {col.median}, std {col.std_dev}"
            f"{null_str}"
        )

    if col.detected_type == "categorical":
        top_str = ", ".join(f"{k}({v})" for k, v in col.top_categories.items())
        return (
            f"  - {col.column_name} (categorical): "
            f"{col.unique_count} unique values total{null_str}. "
            f"Top by frequency: {top_str}. "
            f"Representative samples (not exhaustive): {col.sample_values}"
        )

    if col.detected_type == "datetime":
        return (
            f"  - {col.column_name} (datetime): "
            f"{col.min_value} to {col.max_value}"
            f"{null_str}"
        )

    if col.detected_type == "boolean":
        return (
            f"  - {col.column_name} (boolean): "
            f"{col.unique_count} unique values{null_str}. "
            f"Sample: {col.sample_values}"
        )

    return f"  - {col.column_name} ({col.detected_type}){null_str}"
