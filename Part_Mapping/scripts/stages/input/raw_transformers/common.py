from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

STANDARD_COLUMNS = ["Spec.1", "Spec.2", "Spec.3", "Spec.4", "SpecSummary", "Location", "PutIntoBOM"]


def read_raw_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return _read_ragged_csv(path)
    return pd.read_excel(path, header=None, dtype=str, keep_default_na=False)


def clean_cell(value) -> str:
    return "" if pd.isna(value) else str(value).strip()


def cell_at(values: list[str], idx: int) -> str:
    return values[idx] if idx < len(values) else ""


def join_references(reference_chunks: list[str]) -> str:
    refs: list[str] = []
    for chunk in reference_chunks:
        refs.extend(ref.strip() for ref in str(chunk).split(",") if ref.strip())
    return ",".join(refs)


def _read_ragged_csv(path: str | Path) -> pd.DataFrame:
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        for row in reader:
            rows.append(row)

    if not rows:
        return pd.DataFrame()

    width = max(len(row) for row in rows)
    padded_rows = [row + [""] * (width - len(row)) for row in rows]
    return pd.DataFrame(padded_rows, dtype=str)
