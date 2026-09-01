from __future__ import annotations

from pathlib import Path

import pandas as pd

from .common import STANDARD_COLUMNS, cell_at, clean_cell, join_references, read_raw_table

AMD_LOCATION_COL = 2
AMD_SPEC_COLS = range(3, 9)
AMD_PUT_IN_BOM_COL = 9


def transform_amd_raw_bom(path: str | Path) -> tuple[pd.DataFrame, list[str]]:
    raw_df = read_raw_table(path)
    header_idx = _find_amd_header_row(raw_df)
    warnings: list[str] = []
    errors: list[str] = []
    records: list[dict] = []
    current: dict | None = None

    for row_idx, row in raw_df.iloc[header_idx + 1 :].iterrows():
        excel_row = row_idx + 1
        values = [clean_cell(value) for value in row.tolist()]
        if not any(values):
            continue
        if values[0].startswith("_"):
            continue

        item = values[0]
        reference = cell_at(values, AMD_LOCATION_COL)
        spec_values = [cell_at(values, idx) for idx in AMD_SPEC_COLS]
        put_into_bom = cell_at(values, AMD_PUT_IN_BOM_COL) or "Y"

        if item:
            if not reference:
                errors.append(f"第 {excel_row} 列: 新 item row 的 Location 欄位不可空白。")
            if not any(spec_values):
                errors.append(f"第 {excel_row} 列: column 3-8 至少需要一個 spec 值。")
            if current:
                records.append(current)
            current = {
                "item": item,
                "references": [reference] if reference else [],
                "spec_values": spec_values,
                "put_into_bom": put_into_bom,
            }
            continue

        if reference and current:
            continuation_values = [cell_at(values, idx) for idx in range(3, 10)]
            if any(continuation_values):
                warnings.append(
                    f"第 {excel_row} 列: 延續列只會合併 Location，column 3-9 的值已忽略。"
                )
            current["references"].append(reference)
        elif reference and not current:
            warnings.append(f"第 {excel_row} 列: 略過無主項目的 Reference 延續列: {reference}")

    if current:
        records.append(current)

    if not records:
        errors.append("AMD Raw BOM header 後沒有可轉換的有效資料列。")
    if errors:
        raise ValueError("AMD Raw BOM 格式檢查失敗: " + " ".join(errors))

    rows = []
    for record in records:
        spec_values = [value for value in record["spec_values"] if value]
        rows.append(
            {
                "Spec.1": "",
                "Spec.2": "",
                "Spec.3": "",
                "Spec.4": "",
                "SpecSummary": ", ".join(spec_values),
                "Location": join_references(record["references"]),
                "PutIntoBOM": record["put_into_bom"],
            }
        )

    return pd.DataFrame(rows, columns=STANDARD_COLUMNS), warnings


def _find_amd_header_row(df: pd.DataFrame) -> int:
    for idx, row in df.iterrows():
        values = {clean_cell(value).lower() for value in row.tolist()}
        if {"item", "quantity", "reference", "part"}.issubset(values):
            return idx
    raise ValueError("找不到 AMD Raw BOM 表頭列: Item, Quantity, Reference, Part")
