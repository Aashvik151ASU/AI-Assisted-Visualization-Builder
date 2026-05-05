"""Unit tests for backend/ai_layer.py — all Anthropic calls are mocked."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.ai_layer import VizSpec, generate_insight, interpret_prompt


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_tool_block(overrides: dict | None = None) -> MagicMock:
    """Build a fake tool_use block returned by the mocked Anthropic client."""
    defaults = {
        "chart_type": "bar",
        "x_axis": "department",
        "y_axis": "salary",
        "aggregation": "mean",
        "title": "Average Salary by Department",
        "interpreted_intent": "Show the average salary for each department.",
    }
    if overrides:
        defaults.update(overrides)

    block = MagicMock()
    block.type = "tool_use"
    block.input = defaults
    return block


def _make_usage(
    input_tokens: int = 200,
    cache_read: int = 0,
    cache_write: int = 50,
) -> MagicMock:
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.cache_read_input_tokens = cache_read
    usage.cache_creation_input_tokens = cache_write
    return usage


def _make_response(tool_input: dict | None = None, usage: MagicMock | None = None) -> MagicMock:
    response = MagicMock()
    response.content = [_make_tool_block(tool_input)]
    response.usage = usage or _make_usage()
    return response


# ── VizSpec ────────────────────────────────────────────────────────────────────

class TestVizSpec:
    def test_to_dict_required_fields(self):
        spec = VizSpec(
            chart_type="bar",
            x_axis="region",
            y_axis="revenue",
            aggregation="sum",
            title="Revenue by Region",
            interpreted_intent="Show total revenue per region.",
        )
        d = spec.to_dict()
        assert d["chart_type"] == "bar"
        assert d["x_axis"] == "region"
        assert d["y_axis"] == "revenue"
        assert d["aggregation"] == "sum"
        assert d["title"] == "Revenue by Region"
        assert d["interpreted_intent"] == "Show total revenue per region."

    def test_to_dict_optional_defaults(self):
        spec = VizSpec(
            chart_type="line",
            x_axis="date",
            y_axis="sales",
            aggregation="sum",
            title="Sales Over Time",
            interpreted_intent="Show sales trend.",
        )
        d = spec.to_dict()
        assert d["filters"] == {}
        assert d["grouping"] is None
        assert d["color_encoding"] is None
        assert d["alignment_issues"] == []

    def test_to_dict_with_optional_fields(self):
        spec = VizSpec(
            chart_type="scatter",
            x_axis="age",
            y_axis="salary",
            aggregation="none",
            title="Age vs Salary",
            interpreted_intent="Scatter of age and salary.",
            filters={"region": "West"},
            grouping="department",
            color_encoding="department",
            alignment_issues=["Column 'wage' not found; using 'salary' instead."],
        )
        d = spec.to_dict()
        assert d["filters"] == {"region": "West"}
        assert d["grouping"] == "department"
        assert d["color_encoding"] == "department"
        assert len(d["alignment_issues"]) == 1

    def test_token_fields_not_in_to_dict(self):
        spec = VizSpec(
            chart_type="pie",
            x_axis="category",
            y_axis="count",
            aggregation="count",
            title="Category Distribution",
            interpreted_intent="Distribution of categories.",
            input_tokens=300,
            cache_read_tokens=200,
            cache_write_tokens=100,
        )
        d = spec.to_dict()
        assert "input_tokens" not in d
        assert "cache_read_tokens" not in d
        assert "cache_write_tokens" not in d


# ── interpret_prompt ────────────────────────────────────────────────────────────

SCHEMA = "Dataset: 10 rows × 3 columns\n\nColumns:\n  - department (categorical)\n  - salary (numeric)"


class TestInterpretPrompt:
    """All tests patch anthropic.Anthropic so no real API calls are made."""

    def _patch_client(self, response: MagicMock) -> MagicMock:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = response
        return mock_client

    def test_returns_viz_spec(self):
        mock_client = self._patch_client(_make_response())
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            result = interpret_prompt("Bar chart of salary by department", SCHEMA)
        assert isinstance(result, VizSpec)

    def test_correct_chart_type(self):
        mock_client = self._patch_client(_make_response())
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            result = interpret_prompt("Show salary by department", SCHEMA)
        assert result.chart_type == "bar"

    def test_correct_axes(self):
        mock_client = self._patch_client(_make_response())
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            result = interpret_prompt("Show salary by department", SCHEMA)
        assert result.x_axis == "department"
        assert result.y_axis == "salary"

    def test_aggregation(self):
        mock_client = self._patch_client(_make_response())
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            result = interpret_prompt("Average salary by department", SCHEMA)
        assert result.aggregation == "mean"

    def test_title_extracted(self):
        mock_client = self._patch_client(_make_response())
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            result = interpret_prompt("Show salary by department", SCHEMA)
        assert result.title == "Average Salary by Department"

    def test_interpreted_intent(self):
        mock_client = self._patch_client(_make_response())
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            result = interpret_prompt("Show salary by department", SCHEMA)
        assert result.interpreted_intent != ""

    def test_optional_filters(self):
        mock_client = self._patch_client(
            _make_response(tool_input={"filters": {"department": "Engineering"},
                                       "chart_type": "bar", "x_axis": "department",
                                       "y_axis": "salary", "aggregation": "mean",
                                       "title": "Engineering Salaries",
                                       "interpreted_intent": "Filtered view."})
        )
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            result = interpret_prompt("Engineering salaries", SCHEMA)
        assert result.filters == {"department": "Engineering"}

    def test_filters_defaults_to_empty_dict_when_absent(self):
        mock_client = self._patch_client(_make_response())
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            result = interpret_prompt("Show salary by department", SCHEMA)
        assert result.filters == {}

    def test_optional_grouping(self):
        mock_client = self._patch_client(
            _make_response(tool_input={"grouping": "region",
                                       "chart_type": "bar", "x_axis": "department",
                                       "y_axis": "salary", "aggregation": "mean",
                                       "title": "Salary by Dept & Region",
                                       "interpreted_intent": "Grouped view."})
        )
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            result = interpret_prompt("Group by region", SCHEMA)
        assert result.grouping == "region"

    def test_alignment_issues_captured(self):
        mock_client = self._patch_client(
            _make_response(tool_input={"alignment_issues": ["Column 'wage' not found."],
                                       "chart_type": "bar", "x_axis": "department",
                                       "y_axis": "salary", "aggregation": "mean",
                                       "title": "Salary Chart",
                                       "interpreted_intent": "Show salary."})
        )
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            result = interpret_prompt("Show wage by department", SCHEMA)
        assert "Column 'wage' not found." in result.alignment_issues

    def test_alignment_issues_defaults_empty(self):
        mock_client = self._patch_client(_make_response())
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            result = interpret_prompt("Show salary by department", SCHEMA)
        assert result.alignment_issues == []

    def test_token_counts_populated(self):
        usage = _make_usage(input_tokens=180, cache_read=120, cache_write=60)
        mock_client = self._patch_client(_make_response(usage=usage))
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            result = interpret_prompt("Show salary by department", SCHEMA)
        assert result.input_tokens == 180
        assert result.cache_read_tokens == 120
        assert result.cache_write_tokens == 60

    def test_cache_hit_reflected(self):
        # Second call: all tokens served from cache
        usage = _make_usage(input_tokens=10, cache_read=350, cache_write=0)
        mock_client = self._patch_client(_make_response(usage=usage))
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            result = interpret_prompt("Show salary by department again", SCHEMA)
        assert result.cache_read_tokens == 350
        assert result.cache_write_tokens == 0

    def test_api_called_with_correct_tool_choice(self):
        mock_client = self._patch_client(_make_response())
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            interpret_prompt("Show salary", SCHEMA)
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["tool_choice"] == {
            "type": "tool",
            "name": "extract_visualization_spec",
        }

    def test_api_called_with_cached_system_prompt(self):
        mock_client = self._patch_client(_make_response())
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            interpret_prompt("Show salary", SCHEMA)
        call_kwargs = mock_client.messages.create.call_args[1]
        system = call_kwargs["system"]
        assert isinstance(system, list)
        assert system[0]["cache_control"] == {"type": "ephemeral"}

    def test_schema_context_in_user_message_with_cache(self):
        mock_client = self._patch_client(_make_response())
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            interpret_prompt("Show salary", SCHEMA)
        call_kwargs = mock_client.messages.create.call_args[1]
        user_content = call_kwargs["messages"][0]["content"]
        schema_block = user_content[0]
        assert SCHEMA in schema_block["text"]
        assert schema_block["cache_control"] == {"type": "ephemeral"}

    def test_prompt_text_not_cached(self):
        mock_client = self._patch_client(_make_response())
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            interpret_prompt("Show salary", SCHEMA)
        call_kwargs = mock_client.messages.create.call_args[1]
        user_content = call_kwargs["messages"][0]["content"]
        prompt_block = user_content[1]
        assert "cache_control" not in prompt_block

    def test_all_chart_types(self):
        for chart_type in ("bar", "line", "scatter", "pie", "histogram"):
            mock_client = self._patch_client(
                _make_response(tool_input={"chart_type": chart_type,
                                           "x_axis": "col_a", "y_axis": "col_b",
                                           "aggregation": "count", "title": "T",
                                           "interpreted_intent": "I."})
            )
            with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
                result = interpret_prompt(f"Make a {chart_type}", SCHEMA)
            assert result.chart_type == chart_type


# ── generate_insight ───────────────────────────────────────────────────────────

def _make_text_response(text: str = "Sales peaked in Q3, driven by the West region.") -> MagicMock:
    block = MagicMock()
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


def _base_spec(**kwargs) -> VizSpec:
    defaults = dict(
        chart_type="bar",
        x_axis="region",
        y_axis="revenue",
        aggregation="sum",
        title="Revenue by Region",
        interpreted_intent="Show total revenue per region.",
    )
    defaults.update(kwargs)
    return VizSpec(**defaults)


_BASE_STATS = {
    "row_count": 3,
    "y_min": 100.0,
    "y_max": 300.0,
    "y_mean": 200.0,
    "y_sum": 600.0,
}


class TestGenerateInsight:
    def _patch(self, text: str = "Insight text.") -> MagicMock:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_text_response(text)
        return mock_client

    def test_returns_string(self):
        mock_client = self._patch()
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            result = generate_insight(_base_spec(), _BASE_STATS)
        assert isinstance(result, str)

    def test_returns_non_empty_string(self):
        mock_client = self._patch("Revenue peaked in the North region.")
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            result = generate_insight(_base_spec(), _BASE_STATS)
        assert len(result) > 0

    def test_strips_whitespace(self):
        mock_client = self._patch("  Insight with leading/trailing spaces.  ")
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            result = generate_insight(_base_spec(), _BASE_STATS)
        assert result == "Insight with leading/trailing spaces."

    def test_system_prompt_is_cached(self):
        mock_client = self._patch()
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            generate_insight(_base_spec(), _BASE_STATS)
        call_kwargs = mock_client.messages.create.call_args[1]
        system = call_kwargs["system"]
        assert isinstance(system, list)
        assert system[0]["cache_control"] == {"type": "ephemeral"}

    def test_user_message_contains_spec_fields(self):
        spec = _base_spec(title="Q3 Sales", x_axis="quarter", y_axis="sales")
        mock_client = self._patch()
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            generate_insight(spec, _BASE_STATS)
        call_kwargs = mock_client.messages.create.call_args[1]
        user_text = call_kwargs["messages"][0]["content"]
        assert "Q3 Sales" in user_text
        assert "quarter" in user_text
        assert "sales" in user_text

    def test_user_message_contains_stats(self):
        stats = {"row_count": 5, "y_min": 50.0, "y_max": 999.0, "y_mean": 500.0, "y_sum": 2500.0}
        mock_client = self._patch()
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            generate_insight(_base_spec(), stats)
        call_kwargs = mock_client.messages.create.call_args[1]
        user_text = call_kwargs["messages"][0]["content"]
        assert "999.0" in user_text
        assert "500.0" in user_text

    def test_extra_stat_keys_included(self):
        stats = {**_BASE_STATS, "trend_direction": "upward", "top_category": "West"}
        mock_client = self._patch()
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            generate_insight(_base_spec(), stats)
        call_kwargs = mock_client.messages.create.call_args[1]
        user_text = call_kwargs["messages"][0]["content"]
        assert "upward" in user_text
        assert "West" in user_text

    def test_uses_correct_model(self):
        mock_client = self._patch()
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            generate_insight(_base_spec(), _BASE_STATS)
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-sonnet-4-6"

    def test_max_tokens_bounded(self):
        mock_client = self._patch()
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            generate_insight(_base_spec(), _BASE_STATS)
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["max_tokens"] <= 512

    def test_works_for_each_chart_type(self):
        for chart_type in ("bar", "line", "scatter", "pie", "histogram"):
            mock_client = self._patch(f"Insight for {chart_type}.")
            spec = _base_spec(chart_type=chart_type)
            with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
                result = generate_insight(spec, _BASE_STATS)
            assert isinstance(result, str)

    def test_empty_stats_does_not_crash(self):
        mock_client = self._patch("No stats available.")
        with patch("backend.ai_layer.anthropic.Anthropic", return_value=mock_client):
            result = generate_insight(_base_spec(), {})
        assert isinstance(result, str)
