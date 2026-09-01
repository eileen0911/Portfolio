from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pandas as pd

from .amd import transform_amd_raw_bom

Transformer = Callable[[str | Path], tuple[pd.DataFrame, list[str]]]

STANDARD_BOM_FORMAT = "標準輸入模板，不需轉換"
AMD_RAW_BOM_FORMAT = "AMD Raw BOM"

RAW_BOM_TRANSFORMERS: dict[str, Transformer | None] = {
    STANDARD_BOM_FORMAT: None,
    AMD_RAW_BOM_FORMAT: transform_amd_raw_bom,
}

RAW_BOM_FORMAT_OPTIONS = list(RAW_BOM_TRANSFORMERS)
