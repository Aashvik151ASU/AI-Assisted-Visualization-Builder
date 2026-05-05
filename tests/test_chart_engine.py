"""Unit tests for backend/chart_engine.py."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from backend.ai_layer import VizSpec
from backend.chart_engine import ChartResult, render_chart


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def sales_df() -> pd.DataFrame:
    return pd.DataFrame({
        "region":   ["East", "East", "West", "West", "North"],
        "product":  ["A", "B", "A", "B", "A"],
        "revenue":  [100.0, 200.0, 150.0, 250.0, 300.0],
        "units":    [10, 20, 15, 25, 30],
    })


@pytest.fixture
def numeric_df() -> pd.DataFrame:
    return pd.DataFrame({
        "age":    [25, 30, 35, 40, 45, 50],
        "salary": [50000, 60000, 70000, 80000, 90000, 100000],
    })


def _spec(**kwargs) -> VizSpec:
    defaults = dict(
        chart_type="bar",
        x_axis="region",
        y_axis="revenue",
        aggregation="sum",
        title="Test Chart",
        interpreted_intent="Test intent.",
    )
    defaults.update(kwargs)
    return VizSpec(**defaults)


# ── Chart type rendering ───────────────────────────────────────────────────────

def test_bar_chart_renders(sales_df, tmp_path):
    spec = _spec(chart_type="bar", aggregation="sum")
    result = render_chart(sales_df, spec, output_dir=str(tmp_path))
    assert isinstance(result, ChartResult)
    assert Path(result.output_path).exists()
    assert result.output_path.endswith(".png")
    assert result.chart_type == "bar"


def test_line_chart_renders(sales_df, tmp_path):
    spec = _spec(chart_type="line", aggregation="mean")
    result = render_chart(sales_df, spec, output_dir=str(tmp_path))
    assert Path(result.output_path).exists()
    assert result.chart_type == "line"


def test_scatter_chart_renders(numeric_df, tmp_path):
    spec = _spec(
        chart_type="scatter",
        x_axis="age",
        y_axis="salary",
        aggregation="none",
        title="Age vs Salary",
    )
    result = render_chart(numeric_df, spec, output_dir=str(tmp_path))
    assert Path(result.output_path).exists()
    assert result.chart_type == "scatter"


def test_pie_chart_renders(sales_df, tmp_path):
    spec = _spec(chart_type="pie", aggregation="count", y_axis="count")
    result = render_chart(sales_df, spec, output_dir=str(tmp_path))
    assert Path(result.output_path).exists()
    assert result.chart_type == "pie"


def test_histogram_renders(numeric_df, tmp_path):
    spec = _spec(
        chart_type="histogram",
        x_axis="salary",
        y_axis="salary",
        aggregation="none",
        title="Salary Distribution",
    )
    result = render_chart(numeric_df, spec, output_dir=str(tmp_path))
    assert Path(result.output_path).exists()
    assert result.chart_type == "histogram"


# ── Aggregation ────────────────────────────────────────────────────────────────

def test_aggregation_sum(sales_df, tmp_path):
    spec = _spec(aggregation="sum")
    result = render_chart(sales_df, spec, output_dir=str(tmp_path))
    # East: 300, West: 400, North: 300
    assert result.stats["y_sum"] == pytest.approx(1000.0)


def test_aggregation_mean(sales_df, tmp_path):
    spec = _spec(aggregation="mean")
    result = render_chart(sales_df, spec, output_dir=str(tmp_path))
    # East mean=150, West mean=200, North mean=300 → mean of plot_df = 650/3
    assert result.stats["y_mean"] == pytest.approx(650 / 3, rel=1e-3)


def test_aggregation_count(sales_df, tmp_path):
    spec = _spec(aggregation="count", y_axis="count")
    result = render_chart(sales_df, spec, output_dir=str(tmp_path))
    assert result.stats["row_count"] == 3  # 3 distinct regions after groupby


def test_aggregation_max(sales_df, tmp_path):
    spec = _spec(aggregation="max")
    result = render_chart(sales_df, spec, output_dir=str(tmp_path))
    assert result.stats["y_max"] == pytest.approx(300.0)


def test_aggregation_min(sales_df, tmp_path):
    spec = _spec(aggregation="min")
    result = render_chart(sales_df, spec, output_dir=str(tmp_path))
    assert result.stats["y_min"] == pytest.approx(100.0)


def test_aggregation_none_passes_raw_data(sales_df, tmp_path):
    spec = _spec(aggregation="none")
    result = render_chart(sales_df, spec, output_dir=str(tmp_path))
    assert result.stats["row_count"] == 5  # all rows, no groupby


# ── Filtering ──────────────────────────────────────────────────────────────────

def test_filter_reduces_rows(sales_df, tmp_path):
    spec = _spec(filters={"region": "East"}, aggregation="none")
    result = render_chart(sales_df, spec, output_dir=str(tmp_path))
    assert result.stats["row_count"] == 2


def test_multiple_filters(sales_df, tmp_path):
    spec = _spec(filters={"region": "East", "product": "A"}, aggregation="none")
    result = render_chart(sales_df, spec, output_dir=str(tmp_path))
    assert result.stats["row_count"] == 1


def test_missing_filter_column_skipped(sales_df, tmp_path):
    spec = _spec(filters={"nonexistent_col": "foo"}, aggregation="sum")
    result = render_chart(sales_df, spec, output_dir=str(tmp_path))
    assert result.stats["row_count"] == 3  # all regions, no crash


def test_empty_after_filter_raises(sales_df, tmp_path):
    spec = _spec(filters={"region": "Nonexistent"})
    with pytest.raises(ValueError, match="No data remains"):
        render_chart(sales_df, spec, output_dir=str(tmp_path))


# ── Grouping ───────────────────────────────────────────────────────────────────

def test_grouping_used_when_present(sales_df, tmp_path):
    spec = _spec(aggregation="sum", grouping="product")
    result = render_chart(sales_df, spec, output_dir=str(tmp_path))
    # region × product groups: East/A, East/B, West/A, West/B, North/A = 5 groups
    assert result.stats["row_count"] == 5


def test_absent_grouping_column_ignored(sales_df, tmp_path):
    spec = _spec(aggregation="sum", grouping="nonexistent_col")
    result = render_chart(sales_df, spec, output_dir=str(tmp_path))
    assert result.stats["row_count"] == 3  # just grouped by region, no crash


# ── Stats ──────────────────────────────────────────────────────────────────────

def test_stats_keys_present(sales_df, tmp_path):
    spec = _spec(aggregation="sum")
    result = render_chart(sales_df, spec, output_dir=str(tmp_path))
    for key in ("row_count", "y_min", "y_max", "y_mean", "y_sum"):
        assert key in result.stats


def test_stats_row_count(sales_df, tmp_path):
    spec = _spec(aggregation="sum")
    result = render_chart(sales_df, spec, output_dir=str(tmp_path))
    assert result.stats["row_count"] == 3  # 3 distinct regions


# ── Output file ────────────────────────────────────────────────────────────────

def test_output_path_ends_with_png(sales_df, tmp_path):
    spec = _spec()
    result = render_chart(sales_df, spec, output_dir=str(tmp_path))
    assert result.output_path.endswith(".png")


def test_output_filename_contains_chart_type(sales_df, tmp_path):
    spec = _spec(chart_type="bar")
    result = render_chart(sales_df, spec, output_dir=str(tmp_path))
    assert "bar" in Path(result.output_path).name


def test_output_dir_created_if_missing(sales_df, tmp_path):
    new_dir = tmp_path / "nested" / "dir"
    spec = _spec()
    result = render_chart(sales_df, spec, output_dir=str(new_dir))
    assert new_dir.exists()
    assert Path(result.output_path).exists()


def test_each_call_produces_unique_file(sales_df, tmp_path):
    spec = _spec()
    r1 = render_chart(sales_df, spec, output_dir=str(tmp_path))
    r2 = render_chart(sales_df, spec, output_dir=str(tmp_path))
    assert r1.output_path != r2.output_path
