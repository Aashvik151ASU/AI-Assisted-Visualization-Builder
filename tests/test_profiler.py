"""Unit tests for backend/profiler.py."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.profiler import ColumnProfile, DatasetProfile, profile_dataframe


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def mixed_df() -> pd.DataFrame:
    return pd.DataFrame({
        "region":   ["East", "West", "East", "North", "West"],
        "revenue":  [100.0, 200.0, 150.0, 300.0, 250.0],
        "active":   [True, False, True, True, False],
        "joined":   pd.to_datetime(["2022-01-01", "2022-06-15", "2023-03-10",
                                    "2021-11-20", "2023-07-04"]),
        "headcount":[10, 20, 15, 30, 25],
    })


@pytest.fixture
def numeric_df() -> pd.DataFrame:
    return pd.DataFrame({"salary": [50000, 60000, 70000, 80000, 90000]})


@pytest.fixture
def categorical_df() -> pd.DataFrame:
    return pd.DataFrame({"dept": ["Eng", "HR", "Eng", "Sales", "HR", "Eng"]})


@pytest.fixture
def datetime_df() -> pd.DataFrame:
    return pd.DataFrame({
        "event_date": pd.to_datetime(["2024-01-01", "2024-03-15", "2024-06-30"])
    })


@pytest.fixture
def null_df() -> pd.DataFrame:
    return pd.DataFrame({
        "a": [1.0, None, 3.0, None, 5.0],
        "b": [None, None, None, None, None],
    })


# ── DatasetProfile shape ───────────────────────────────────────────────────────

class TestDatasetProfile:
    def test_row_count(self, mixed_df):
        profile = profile_dataframe(mixed_df)
        assert profile.row_count == 5

    def test_column_count(self, mixed_df):
        profile = profile_dataframe(mixed_df)
        assert profile.column_count == 5

    def test_columns_list_length(self, mixed_df):
        profile = profile_dataframe(mixed_df)
        assert len(profile.columns) == 5

    def test_column_names_match(self, mixed_df):
        profile = profile_dataframe(mixed_df)
        names = [c.column_name for c in profile.columns]
        assert set(names) == set(mixed_df.columns)

    def test_to_dict_keys(self, mixed_df):
        d = profile_dataframe(mixed_df).to_dict()
        assert "row_count" in d
        assert "column_count" in d
        assert "columns" in d
        assert isinstance(d["columns"], list)

    def test_to_dict_column_count_matches(self, mixed_df):
        d = profile_dataframe(mixed_df).to_dict()
        assert len(d["columns"]) == mixed_df.shape[1]


# ── Type detection ─────────────────────────────────────────────────────────────

class TestTypeDetection:
    def test_numeric_detected(self, numeric_df):
        profile = profile_dataframe(numeric_df)
        col = profile.columns[0]
        assert col.detected_type == "numeric"

    def test_categorical_detected(self, categorical_df):
        profile = profile_dataframe(categorical_df)
        col = profile.columns[0]
        assert col.detected_type == "categorical"

    def test_datetime_detected(self, datetime_df):
        profile = profile_dataframe(datetime_df)
        col = profile.columns[0]
        assert col.detected_type == "datetime"

    def test_boolean_detected(self):
        df = pd.DataFrame({"flag": [True, False, True, False]})
        profile = profile_dataframe(df)
        col = profile.columns[0]
        assert col.detected_type == "boolean"

    def test_mixed_df_types(self, mixed_df):
        profile = profile_dataframe(mixed_df)
        type_map = {c.column_name: c.detected_type for c in profile.columns}
        assert type_map["region"] == "categorical"
        assert type_map["revenue"] == "numeric"
        assert type_map["active"] == "boolean"
        assert type_map["joined"] == "datetime"
        assert type_map["headcount"] == "numeric"


# ── Null percentage ────────────────────────────────────────────────────────────

class TestNullPercentage:
    def test_no_nulls_zero_pct(self, numeric_df):
        profile = profile_dataframe(numeric_df)
        assert profile.columns[0].null_percentage == 0.0

    def test_partial_nulls(self, null_df):
        profile = profile_dataframe(null_df)
        col_a = next(c for c in profile.columns if c.column_name == "a")
        assert col_a.null_percentage == pytest.approx(40.0)

    def test_all_null_100_pct(self, null_df):
        profile = profile_dataframe(null_df)
        col_b = next(c for c in profile.columns if c.column_name == "b")
        assert col_b.null_percentage == 100.0


# ── Unique count ───────────────────────────────────────────────────────────────

class TestUniqueCount:
    def test_unique_count_categorical(self, categorical_df):
        profile = profile_dataframe(categorical_df)
        col = profile.columns[0]
        assert col.unique_count == 3  # Eng, HR, Sales

    def test_unique_count_numeric_all_distinct(self, numeric_df):
        profile = profile_dataframe(numeric_df)
        col = profile.columns[0]
        assert col.unique_count == 5

    def test_unique_count_with_repeats(self):
        df = pd.DataFrame({"x": [1, 1, 2, 2, 3]})
        profile = profile_dataframe(df)
        assert profile.columns[0].unique_count == 3


# ── Numeric statistics ─────────────────────────────────────────────────────────

class TestNumericStats:
    def test_min_value(self, numeric_df):
        profile = profile_dataframe(numeric_df)
        col = profile.columns[0]
        assert col.min_value == pytest.approx(50000.0)

    def test_max_value(self, numeric_df):
        profile = profile_dataframe(numeric_df)
        col = profile.columns[0]
        assert col.max_value == pytest.approx(90000.0)

    def test_mean_value(self, numeric_df):
        profile = profile_dataframe(numeric_df)
        col = profile.columns[0]
        assert col.mean == pytest.approx(70000.0)

    def test_median_value(self, numeric_df):
        profile = profile_dataframe(numeric_df)
        col = profile.columns[0]
        assert col.median == pytest.approx(70000.0)

    def test_std_dev_positive(self, numeric_df):
        profile = profile_dataframe(numeric_df)
        col = profile.columns[0]
        assert col.std_dev > 0

    def test_numeric_stats_none_for_categorical(self, categorical_df):
        profile = profile_dataframe(categorical_df)
        col = profile.columns[0]
        assert col.min_value is None
        assert col.max_value is None
        assert col.mean is None


# ── Datetime statistics ────────────────────────────────────────────────────────

class TestDatetimeStats:
    def test_min_date(self, datetime_df):
        profile = profile_dataframe(datetime_df)
        col = profile.columns[0]
        assert col.min_value == "2024-01-01"

    def test_max_date(self, datetime_df):
        profile = profile_dataframe(datetime_df)
        col = profile.columns[0]
        assert col.max_value == "2024-06-30"

    def test_no_mean_for_datetime(self, datetime_df):
        profile = profile_dataframe(datetime_df)
        col = profile.columns[0]
        assert col.mean is None


# ── Categorical statistics ─────────────────────────────────────────────────────

class TestCategoricalStats:
    def test_top_categories_populated(self, categorical_df):
        profile = profile_dataframe(categorical_df)
        col = profile.columns[0]
        assert len(col.top_categories) > 0

    def test_top_categories_most_frequent_first(self, categorical_df):
        profile = profile_dataframe(categorical_df)
        col = profile.columns[0]
        counts = list(col.top_categories.values())
        assert counts == sorted(counts, reverse=True)

    def test_top_categories_max_5(self):
        # 10 distinct categories — top_categories should cap at 5
        df = pd.DataFrame({"cat": [str(i) for i in range(10)] * 3})
        profile = profile_dataframe(df)
        col = profile.columns[0]
        assert len(col.top_categories) <= 5

    def test_top_categories_empty_for_numeric(self, numeric_df):
        profile = profile_dataframe(numeric_df)
        col = profile.columns[0]
        assert col.top_categories == {}


# ── Sample values ──────────────────────────────────────────────────────────────

class TestSampleValues:
    def test_sample_values_max_5(self):
        df = pd.DataFrame({"x": list(range(20))})
        profile = profile_dataframe(df)
        assert len(profile.columns[0].sample_values) <= 5

    def test_sample_values_are_serialisable(self, mixed_df):
        import json
        profile = profile_dataframe(mixed_df)
        for col in profile.columns:
            json.dumps(col.sample_values)  # must not raise

    def test_sample_values_no_nan(self, null_df):
        profile = profile_dataframe(null_df)
        for col in profile.columns:
            for v in col.sample_values:
                assert v is not None

    def test_datetime_samples_are_strings(self, datetime_df):
        profile = profile_dataframe(datetime_df)
        col = profile.columns[0]
        for v in col.sample_values:
            assert isinstance(v, str)

    def test_bool_samples_are_python_bool(self):
        df = pd.DataFrame({"flag": [True, False, True]})
        profile = profile_dataframe(df)
        col = profile.columns[0]
        for v in col.sample_values:
            assert isinstance(v, bool)


# ── LLM context ────────────────────────────────────────────────────────────────

class TestLLMContext:
    def test_to_llm_context_is_string(self, mixed_df):
        ctx = profile_dataframe(mixed_df).to_llm_context()
        assert isinstance(ctx, str)

    def test_to_llm_context_contains_row_count(self, mixed_df):
        ctx = profile_dataframe(mixed_df).to_llm_context()
        assert "5" in ctx

    def test_to_llm_context_contains_all_column_names(self, mixed_df):
        ctx = profile_dataframe(mixed_df).to_llm_context()
        for col in mixed_df.columns:
            assert col in ctx

    def test_to_llm_context_contains_type_labels(self, mixed_df):
        ctx = profile_dataframe(mixed_df).to_llm_context()
        for label in ("numeric", "categorical", "datetime", "boolean"):
            assert label in ctx

    def test_to_llm_context_numeric_stats_present(self, numeric_df):
        ctx = profile_dataframe(numeric_df).to_llm_context()
        assert "mean" in ctx or "70000" in ctx

    def test_to_llm_context_not_empty(self, mixed_df):
        ctx = profile_dataframe(mixed_df).to_llm_context()
        assert len(ctx) > 50


# ── ColumnProfile.to_dict ──────────────────────────────────────────────────────

class TestColumnProfileToDict:
    def test_required_keys_present(self, numeric_df):
        profile = profile_dataframe(numeric_df)
        d = profile.columns[0].to_dict()
        for key in ("column_name", "detected_type", "null_percentage",
                    "unique_count", "sample_values"):
            assert key in d

    def test_numeric_keys_present(self, numeric_df):
        d = profile_dataframe(numeric_df).columns[0].to_dict()
        for key in ("min_value", "max_value", "mean", "median", "std_dev"):
            assert key in d

    def test_categorical_top_categories_in_dict(self, categorical_df):
        d = profile_dataframe(categorical_df).columns[0].to_dict()
        assert "top_categories" in d
        assert isinstance(d["top_categories"], dict)

    def test_single_row_df_handled(self):
        df = pd.DataFrame({"x": [42], "label": ["only"]})
        profile = profile_dataframe(df)
        assert profile.row_count == 1
        assert len(profile.columns) == 2
