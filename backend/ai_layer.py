from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import anthropic

from backend.config import settings
from backend.guardrails import (
    GuardrailViolation,
    sanitize_insight,
    sanitize_title,
    validate_input,
    validate_viz_spec_output,
)

MODEL = "claude-sonnet-4-6"


def _make_client() -> anthropic.Anthropic:
    kwargs: dict = {"api_key": settings.anthropic_api_key}
    if settings.anthropic_base_url:
        kwargs["base_url"] = settings.anthropic_base_url
        kwargs["default_headers"] = {"x-session-id": "ai-viz-builder"}
    return anthropic.Anthropic(**kwargs)


def _extract_text(response: Any) -> str:
    """Pull plain text out of whatever the proxy returns."""
    if isinstance(response, str):
        return response
    if hasattr(response, "content"):
        blocks = response.content
        if isinstance(blocks, list):
            parts = []
            for b in blocks:
                if hasattr(b, "text"):
                    parts.append(b.text)
                elif isinstance(b, str):
                    parts.append(b)
            return "\n".join(parts)
        if isinstance(blocks, str):
            return blocks
    return str(response)


def _parse_json_from_text(text: str) -> dict:
    """Extract the first JSON object found in a text response, ignoring trailing content."""
    decoder = json.JSONDecoder()
    # Strip markdown fences if present
    fenced = re.search(r"```(?:json)?\s*(\{.*)", text, re.DOTALL)
    search_text = fenced.group(1) if fenced else text
    # Find the first { and decode from there — stops at the end of the object
    idx = search_text.find("{")
    if idx == -1:
        raise ValueError(f"No JSON object found in response: {text[:300]}")
    obj, _ = decoder.raw_decode(search_text, idx)
    return obj


_INSIGHT_SYSTEM = """\
You are a business intelligence analyst. Given a chart specification and computed statistics,
write a 2–3 sentence plain-English insight summary that a non-technical business user would
find immediately useful. Focus on the key finding, the standout value or trend, and any
actionable implication. Do not describe chart mechanics — describe what the data means.
Output only the summary sentences, nothing else.\
"""

_SYSTEM_PROMPT = """\
You are a data visualization expert. Given a dataset schema and a user's natural language
request, return a JSON object specifying the chart to render.

Rules:
- Only use column names that exist in the dataset schema.
- If the user mentions a column that does not exist, add a note in alignment_issues and
  suggest the closest matching column name from the schema.
- Choose the most appropriate chart type for the data shape and the user's intent:
    bar       → compare categories
    line      → trends over time or ordered data
    scatter   → relationship between two numeric columns
    pie       → part-to-whole with few categories (≤8)
    histogram → distribution of a single numeric column
- aggregation must be one of: sum | mean | count | max | min | none
- filters: ONLY add a filter when the user EXPLICITLY asks to restrict the data to a
  specific value (e.g. "only show Q1", "just for the West region"). The schema context
  shows sample/top values for reference — do NOT use them to set filters. Default: {}.
- The chart must represent the ENTIRE dataset (after any user-requested filters).
  Never limit or sample rows; aggregation handles large datasets automatically.
- grouping is the column used to split series within the same chart (optional).
- interpreted_intent is a single plain-English sentence summarising what the user wants.
- Always produce a concise, business-friendly chart title.

Respond with ONLY a valid JSON object — no markdown, no explanation. Example shape:
{
  "chart_type": "bar",
  "x_axis": "region",
  "y_axis": "revenue",
  "aggregation": "sum",
  "filters": {},
  "grouping": null,
  "title": "Total Revenue by Region",
  "color_encoding": null,
  "interpreted_intent": "Show total revenue broken down by region.",
  "alignment_issues": []
}\
"""


# ── Return type ────────────────────────────────────────────────────────────────

@dataclass
class VizSpec:
    chart_type:         str
    x_axis:             str
    y_axis:             str
    aggregation:        str
    title:              str
    interpreted_intent: str
    filters:            dict[str, Any] = field(default_factory=dict)
    grouping:           str | None     = None
    color_encoding:     str | None     = None
    alignment_issues:   list[str]      = field(default_factory=list)
    agg_axis:           str            = "y"   # "y" or "x" — which axis the aggregation applies to
    input_tokens:       int            = 0
    cache_read_tokens:  int            = 0
    cache_write_tokens: int            = 0

    def to_dict(self) -> dict:
        return {
            "chart_type":         self.chart_type,
            "x_axis":             self.x_axis,
            "y_axis":             self.y_axis,
            "aggregation":        self.aggregation,
            "agg_axis":           self.agg_axis,
            "title":              self.title,
            "interpreted_intent": self.interpreted_intent,
            "filters":            self.filters,
            "grouping":           self.grouping,
            "color_encoding":     self.color_encoding,
            "alignment_issues":   self.alignment_issues,
        }


# ── Public functions ───────────────────────────────────────────────────────────

def interpret_prompt(prompt_text: str, schema_context: str) -> VizSpec:
    """
    Interpret a natural language chart request against a dataset schema.
    Uses a plain-text JSON response (no tool use) for maximum proxy compatibility.

    Raises GuardrailViolation if the prompt fails input safety checks.
    """
    # ── Input guardrail ────────────────────────────────────────────────────────
    validate_input(prompt_text)

    client = _make_client()

    with client.messages.stream(
        model=MODEL,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Dataset Schema:\n{schema_context}\n\n"
                    f"User Request: {prompt_text}"
                ),
            }
        ],
    ) as stream:
        text = stream.get_final_text()

    raw = _parse_json_from_text(text)

    # ── Output guardrail ───────────────────────────────────────────────────────
    validate_viz_spec_output(raw)   # logs warnings; does not raise

    return VizSpec(
        chart_type=raw["chart_type"],
        x_axis=raw["x_axis"],
        y_axis=raw["y_axis"],
        aggregation=raw["aggregation"],
        title=sanitize_title(raw["title"]),
        interpreted_intent=raw["interpreted_intent"],
        filters=raw.get("filters") or {},
        grouping=raw.get("grouping"),
        color_encoding=raw.get("color_encoding"),
        alignment_issues=raw.get("alignment_issues") or [],
    )


# ── Insight generation ─────────────────────────────────────────────────────────

def generate_insight(spec: VizSpec, stats: dict[str, Any]) -> str:
    """Generate a 2–3 sentence natural language insight summary for a rendered chart."""
    client = _make_client()

    all_values = stats.get("all_values", {})
    value_lines = "\n".join(f"  {k}: {v}" for k, v in all_values.items()) if all_values else ""
    other_stats = {k: v for k, v in stats.items() if k != "all_values"}
    stat_lines = "\n".join(f"  {k}: {v}" for k, v in other_stats.items())

    context = (
        f"Chart title: {spec.title}\n"
        f"Chart type: {spec.chart_type}\n"
        f"X-axis: {spec.x_axis}\n"
        f"Y-axis: {spec.y_axis}\n"
        f"Aggregation: {spec.aggregation}\n"
        f"User intent: {spec.interpreted_intent}\n"
        f"\nActual data values ({spec.x_axis} → {spec.y_axis}):\n{value_lines}\n"
        f"\nSummary statistics:\n{stat_lines}"
    )

    with client.messages.stream(
        model=MODEL,
        max_tokens=256,
        system=_INSIGHT_SYSTEM,
        messages=[{"role": "user", "content": context}],
    ) as stream:
        raw_insight = stream.get_final_text().strip()

    # ── Output guardrail ───────────────────────────────────────────────────────
    safe_insight, _ = sanitize_insight(raw_insight)
    return safe_insight


# ── Auto-suggestions (text only) ──────────────────────────────────────────────

_SUGGEST_SYSTEM = """\
You are a data visualization expert. Given a dataset schema, suggest 5 specific and varied
chart ideas that would reveal useful business insights from this data.

Rules:
- Each suggestion must be a single plain-English sentence a user would type as a prompt.
- Use the actual column names from the schema naturally (e.g. "Show total revenue by region").
- Cover a variety of chart types and analytical angles (comparison, distribution, trend, etc).
- Make each suggestion concrete and immediately actionable — no vague generalities.
- Return ONLY a JSON array of 5 strings, nothing else. Example:
  ["Show total revenue by region as a bar chart", "Plot the distribution of salaries as a histogram", ...]
"""


def suggest_visualizations(schema_context: str) -> list[str]:
    """Return 5 chart prompt suggestions tailored to the uploaded dataset's schema."""
    client = _make_client()

    with client.messages.stream(
        model=MODEL,
        max_tokens=512,
        system=_SUGGEST_SYSTEM,
        messages=[{"role": "user", "content": f"Dataset Schema:\n{schema_context}"}],
    ) as stream:
        text = stream.get_final_text().strip()

    try:
        suggestions = json.loads(text)
        if isinstance(suggestions, list):
            return [str(s) for s in suggestions[:5]]
    except (json.JSONDecodeError, ValueError):
        pass

    return re.findall(r'"([^"]{10,})"', text)[:5]


# ── Auto-preview: structured specs ────────────────────────────────────────────

_SUGGEST_SPEC_SYSTEM = """\
You are a data visualization expert. Given a dataset schema, produce 5 specific and varied
chart specifications that reveal useful business insights from this data.

Rules:
- Only use column names that exist in the dataset schema.
- Cover varied chart types across the 5 suggestions: bar, line, scatter, pie, histogram.
- For histogram: set y_axis to the same column as x_axis.
- For pie: x_axis should be a categorical column with ≤ 8 unique values.
- aggregation must be one of: sum | mean | count | max | min | none
- filters must always be {} — these are overview charts of the full dataset, not subsets.
- "suggestion" is a plain-English sentence the user would type as a prompt.

Return ONLY a valid JSON array of exactly 5 objects, nothing else:
[
  {
    "suggestion": "Show total revenue by region as a bar chart",
    "chart_type": "bar",
    "x_axis": "column_name",
    "y_axis": "column_name",
    "aggregation": "sum",
    "title": "Human-friendly chart title",
    "filters": {},
    "grouping": null,
    "color_encoding": null
  }
]\
"""


def suggest_with_specs(schema_context: str) -> list[tuple[VizSpec, str]]:
    """Return up to 5 (VizSpec, suggestion_text) pairs for auto-preview rendering."""
    client = _make_client()

    with client.messages.stream(
        model=MODEL,
        max_tokens=1024,
        system=_SUGGEST_SPEC_SYSTEM,
        messages=[{"role": "user", "content": f"Dataset Schema:\n{schema_context}"}],
    ) as stream:
        text = stream.get_final_text().strip()

    try:
        raw_list = json.loads(text)
    except json.JSONDecodeError:
        fenced = re.search(r"```(?:json)?\s*(\[.*)", text, re.DOTALL)
        if fenced:
            text = fenced.group(1).rstrip("`").strip()
        try:
            raw_list = json.loads(text)
        except json.JSONDecodeError:
            return []

    if not isinstance(raw_list, list):
        return []

    results: list[tuple[VizSpec, str]] = []
    for item in raw_list[:5]:
        if not isinstance(item, dict):
            continue
        try:
            spec = VizSpec(
                chart_type=item["chart_type"],
                x_axis=item["x_axis"],
                y_axis=item["y_axis"],
                aggregation=item["aggregation"],
                title=item.get("title", ""),
                interpreted_intent=item.get("suggestion", ""),
                filters=item.get("filters") or {},
                grouping=item.get("grouping"),
                color_encoding=item.get("color_encoding"),
            )
            results.append((spec, item.get("suggestion", spec.title)))
        except (KeyError, TypeError):
            continue

    return results

