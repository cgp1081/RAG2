"""Schema inference helpers for structured (tabular) ingestion."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from slugify import slugify


@dataclass(slots=True)
class ColumnDefinition:
    name: str
    slug: str
    data_type: str
    nullable: bool
    is_primary_key: bool
    sample_values: list[str]
    stats: dict[str, float | int | list[str]]


def slugify_name(name: str) -> str:
    """Create a slug for column names using snake_case.

    Ensures a fallback slug when values are blank (e.g. unnamed columns).
    """

    base = slugify(name or "column", separator="_")
    return base or "column"


def guess_primary_key(df: pd.DataFrame) -> str | None:
    """Return the most likely primary key column name, if any."""

    if df.empty:
        return None

    candidates: list[tuple[int, str]] = []
    row_count = len(df)
    for column in df.columns:
        series = df[column]
        if series.isna().any():
            continue
        # Ensure uniqueness when compared to overall row count.
        if series.nunique(dropna=False) != row_count:
            continue
        score = 1
        lower = column.lower()
        if lower in {"id", "uuid"} or lower.endswith("_id"):
            score = 0
        candidates.append((score, column))

    if not candidates:
        return None

    candidates.sort()
    return candidates[0][1]


def infer_schema(df: pd.DataFrame, sample_size: int = 5) -> list[ColumnDefinition]:
    """Infer column metadata for a dataframe."""

    if df.empty:
        return []

    primary_key = guess_primary_key(df)
    seen_slugs: set[str] = set()
    columns: list[ColumnDefinition] = []

    for column in df.columns:
        series = df[column]
        slug = _unique_slug(slugify_name(str(column)), seen_slugs)
        data_type = _infer_type(series)
        nullable = bool(series.isna().any())
        sample_values = (
            series.dropna().astype(str).head(sample_size).tolist()
        )
        most_common = (
            series.dropna()
            .astype(str)
            .value_counts()
            .head(sample_size)
            .index.tolist()
        )
        null_ratio = float(series.isna().sum()) / len(series)
        stats = {
            "null_ratio": round(null_ratio, 4),
            "distinct_count": int(series.nunique(dropna=True)),
            "most_common": most_common,
        }
        definition = ColumnDefinition(
            name=str(column),
            slug=slug,
            data_type=data_type,
            nullable=nullable,
            is_primary_key=column == primary_key,
            sample_values=sample_values,
            stats=stats,
        )
        columns.append(definition)

    return columns


def _unique_slug(candidate: str, seen: set[str]) -> str:
    if candidate not in seen:
        seen.add(candidate)
        return candidate

    index = 2
    while f"{candidate}_{index}" in seen:
        index += 1
    slug = f"{candidate}_{index}"
    seen.add(slug)
    return slug


def _infer_type(series: pd.Series) -> str:
    dtype = series.dtype
    if pd.api.types.is_bool_dtype(dtype):
        return "boolean"
    if pd.api.types.is_integer_dtype(dtype):
        return "integer"
    if pd.api.types.is_float_dtype(dtype):
        return "float"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "datetime"
    if pd.api.types.is_string_dtype(dtype):
        return "string"

    # Attempt to coerce to datetime/bool heuristically for object columns
    if pd.api.types.is_object_dtype(dtype):
        if _looks_like_bool(series):
            return "boolean"
        if _looks_like_datetime(series):
            return "datetime"
    return "string"


def _looks_like_bool(series: pd.Series) -> bool:
    sample = {str(value).strip().lower() for value in series.dropna().head(20)}
    return bool(sample) and sample.issubset({"true", "false", "1", "0", "yes", "no"})


def _looks_like_datetime(series: pd.Series) -> bool:
    sample = series.dropna().head(20)
    if sample.empty:
        return False
    try:
        pd.to_datetime(sample, errors="raise")
        return True
    except Exception:
        return False


__all__ = [
    "ColumnDefinition",
    "infer_schema",
    "guess_primary_key",
    "slugify_name",
]
