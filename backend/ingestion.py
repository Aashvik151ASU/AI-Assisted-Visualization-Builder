from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from backend.config import settings

# Column names that should never hold negative values
_NON_NEGATIVE_PATTERN = re.compile(
    r"(salary|wage|price|amount|revenue|cost|quantity|qty|count|age|headcount|hours|sales)",
    re.IGNORECASE,
)

_LOADERS: dict[str, callable] = {
    "csv":     lambda b: pd.read_csv(io.BytesIO(b)),
    "xlsx":    lambda b: pd.read_excel(io.BytesIO(b)),
    "json":    lambda b: pd.read_json(io.BytesIO(b)),
    "parquet": lambda b: pd.read_parquet(io.BytesIO(b)),
}


# ── Report types ───────────────────────────────────────────────────────────────

@dataclass
class ColumnIssue:
    column: str
    level: str  # "error" | "warning"
    message: str


@dataclass
class ValidationReport:
    file_name: str
    row_count: int
    column_count: int
    duplicate_count: int = 0
    null_percentages: dict[str, float] = field(default_factory=dict)
    column_types: dict[str, str] = field(default_factory=dict)
    issues: list[ColumnIssue] = field(default_factory=list)
    warnings: list[ColumnIssue] = field(default_factory=list)
    passed: bool = True

    def add_issue(self, column: str, message: str) -> None:
        self.issues.append(ColumnIssue(column=column, level="error", message=message))
        self.passed = False

    def add_warning(self, column: str, message: str) -> None:
        self.warnings.append(ColumnIssue(column=column, level="warning", message=message))

    def to_dict(self) -> dict:
        return {
            "file_name": self.file_name,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "duplicate_count": self.duplicate_count,
            "null_percentages": self.null_percentages,
            "column_types": self.column_types,
            "issues": [
                {"column": i.column, "level": i.level, "message": i.message}
                for i in self.issues
            ],
            "warnings": [
                {"column": w.column, "level": w.level, "message": w.message}
                for w in self.warnings
            ],
            "passed": self.passed,
        }


# ── Public entry points ────────────────────────────────────────────────────────

def ingest_upload(file_name: str, content: bytes) -> tuple[pd.DataFrame, ValidationReport]:
    """Parse and validate a file received as raw bytes (API upload path)."""
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.max_upload_size_mb:
        raise ValueError(
            f"File size {size_mb:.1f} MB exceeds the {settings.max_upload_size_mb} MB limit."
        )

    ext = Path(file_name).suffix.lower().lstrip(".")
    if ext not in settings.allowed_extensions_list:
        raise ValueError(
            f"Unsupported file type '.{ext}'. "
            f"Accepted: {', '.join(settings.allowed_extensions_list)}"
        )

    try:
        df = _LOADERS[ext](content)
    except Exception as exc:
        raise ValueError(f"Could not parse '{file_name}': {exc}") from exc

    return _run_validation(df, file_name)


def ingest_file(path: str | Path) -> tuple[pd.DataFrame, ValidationReport]:
    """Parse and validate a file already on disk (tests / CLI usage)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return ingest_upload(path.name, path.read_bytes())


# ── Validation pipeline ────────────────────────────────────────────────────────

def _run_validation(df: pd.DataFrame, file_name: str) -> tuple[pd.DataFrame, ValidationReport]:
    report = ValidationReport(
        file_name=file_name,
        row_count=len(df),
        column_count=len(df.columns),
    )
    _check_schema(df, report)
    _check_nulls(df, report)
    _check_duplicates(df, report)
    df = _standardize_types(df, report)
    _check_ranges(df, report)
    return df, report


def _check_schema(df: pd.DataFrame, report: ValidationReport) -> None:
    if df.empty:
        report.add_issue("(file)", "File is empty — no rows could be parsed.")
        return

    cols = list(df.columns)
    unnamed = [c for c in cols if str(c).startswith("Unnamed:")]
    if len(unnamed) == len(cols):
        report.add_issue("(headers)", "All columns are unnamed — file may be missing a header row.")
    elif unnamed:
        report.add_warning("(headers)", f"{len(unnamed)} column(s) have auto-generated names: {unnamed}")

    duplicate_cols = {c for c in cols if cols.count(c) > 1}
    if duplicate_cols:
        report.add_issue("(headers)", f"Duplicate column names: {sorted(duplicate_cols)}")


def _check_nulls(df: pd.DataFrame, report: ValidationReport) -> None:
    for col in df.columns:
        pct = round(df[col].isna().mean() * 100, 1)
        report.null_percentages[col] = pct
        if pct == 100.0:
            report.add_issue(col, "Column is entirely null.")
        elif pct >= 50.0:
            report.add_warning(col, f"{pct}% of values are missing.")
        elif pct > 0:
            report.add_warning(col, f"{pct}% of values are missing.")


def _check_duplicates(df: pd.DataFrame, report: ValidationReport) -> None:
    dup_count = int(df.duplicated().sum())
    report.duplicate_count = dup_count
    if dup_count:
        report.add_warning("(rows)", f"{dup_count} duplicate row(s) found.")


def _standardize_types(df: pd.DataFrame, report: ValidationReport) -> pd.DataFrame:
    """Coerce object columns to numeric or datetime where ≥90% of values convert cleanly."""
    df = df.copy()

    for col in df.select_dtypes(include="object").columns:
        # Numeric coercion
        as_numeric = pd.to_numeric(df[col], errors="coerce")
        if as_numeric.notna().mean() >= 0.9:
            df[col] = as_numeric
            report.column_types[col] = "numeric"
            report.add_warning(col, "Text column coerced to numeric.")
            continue

        # Datetime coercion (pandas 2.x compatible)
        try:
            as_dt = pd.to_datetime(df[col], format="mixed", dayfirst=False, errors="coerce")
        except TypeError:
            # fallback for older pandas
            as_dt = pd.to_datetime(df[col], infer_datetime_format=True, errors="coerce")

        if as_dt.notna().mean() >= 0.9:
            formats_seen = _detect_date_formats(df[col].dropna().astype(str).head(50))
            if len(formats_seen) > 1:
                report.add_warning(
                    col,
                    f"Mixed date formats detected {formats_seen} — standardized to ISO 8601.",
                )
            df[col] = as_dt
            report.column_types[col] = "datetime"
            continue

        report.column_types[col] = "categorical"

    # Tag remaining native types
    for col in df.select_dtypes(include=["int64", "float64"]).columns:
        report.column_types.setdefault(col, "numeric")
    for col in df.select_dtypes(include=["datetime64"]).columns:
        report.column_types.setdefault(col, "datetime")
    for col in df.select_dtypes(include=["bool"]).columns:
        report.column_types.setdefault(col, "boolean")

    return df


def _detect_date_formats(sample: pd.Series) -> set[str]:
    patterns = {
        "YYYY-MM-DD": re.compile(r"^\d{4}-\d{2}-\d{2}"),
        "MM/DD/YYYY": re.compile(r"^\d{2}/\d{2}/\d{4}"),
        "DD-MM-YYYY": re.compile(r"^\d{2}-\d{2}-\d{4}"),
        "DD/MM/YYYY": re.compile(r"^\d{2}/\d{2}/\d{4}"),
    }
    found: set[str] = set()
    for val in sample:
        for fmt, pat in patterns.items():
            if pat.match(val):
                found.add(fmt)
                break
    return found


def _check_ranges(df: pd.DataFrame, report: ValidationReport) -> None:
    for col in df.select_dtypes(include="number").columns:
        if _NON_NEGATIVE_PATTERN.search(col):
            neg_count = int((df[col] < 0).sum())
            if neg_count:
                report.add_warning(
                    col,
                    f"{neg_count} negative value(s) in '{col}', which is expected to be non-negative.",
                )


