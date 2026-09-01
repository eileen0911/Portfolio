from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = [
    "Spec.1",
    "Spec.2",
    "Spec.3",
    "Spec.4",
    "PutIntoBOM",
    "SpecSummary",
    "Location",
]

SPEC_COLUMNS = ["Spec.1", "Spec.2", "Spec.3", "Spec.4"]
REVIEW_COLUMNS = ["Row", "Column", "Issue", "Value"]
EXCLUDED_PUT_IN_BOM_VALUES = {"N", "DNI", "DEBUG"}


@dataclass
class ValidationResult:
    valid: bool
    errors: pd.DataFrame
    warnings: pd.DataFrame
    preview_df: pd.DataFrame


def validate_bom_template(path: str | Path) -> ValidationResult:
    df = read_bom_table(path)
    errors: list[dict] = []
    warnings: list[dict] = []

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    for col in missing:
        errors.append(
            {
                "Row": "Header",
                "Column": col,
                "Issue": "Missing required column",
                "Value": "",
            }
        )

    if missing:
        return ValidationResult(
            valid=False,
            errors=pd.DataFrame(errors, columns=REVIEW_COLUMNS),
            warnings=pd.DataFrame(warnings, columns=REVIEW_COLUMNS),
            preview_df=df.head(20),
        )

    for idx, row in df.iterrows():
        excel_row = idx + 2
        put_value = row.get("PutIntoBOM", "")
        put = "" if pd.isna(put_value) else str(put_value).strip().upper()
        location_raw = row.get("Location", "")
        location = "" if pd.isna(location_raw) else str(location_raw).strip()
        spec_summary_raw = row.get("SpecSummary", "")
        spec_summary = "" if pd.isna(spec_summary_raw) else str(spec_summary_raw).strip()
        spec_values = []
        for col in SPEC_COLUMNS:
            val = row.get(col, "")
            if pd.notna(val) and str(val).strip():
                spec_values.append(str(val).strip())

        if put not in EXCLUDED_PUT_IN_BOM_VALUES and not spec_summary and not spec_values:
            errors.append(
                {
                    "Row": excel_row,
                    "Column": "SpecSummary",
                    "Issue": "SpecSummary or at least one Spec column is required for mapping rows",
                    "Value": "",
                }
            )

        if put not in EXCLUDED_PUT_IN_BOM_VALUES and location and ";" in location:
            warnings.append(
                {
                    "Row": excel_row,
                    "Column": "Location",
                    "Issue": "Use commas to separate multiple locations",
                    "Value": location,
                }
            )

    return ValidationResult(
        valid=len(errors) == 0,
        errors=pd.DataFrame(errors, columns=REVIEW_COLUMNS),
        warnings=pd.DataFrame(warnings, columns=REVIEW_COLUMNS),
        preview_df=df.head(20),
    )


def read_bom_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)
