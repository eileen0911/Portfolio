from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).parent.parent

APP_VERSION = "0.3.0"
APP_BUILD = "2026-09-01"

# Public demo defaults. Override with environment variables in a local/private setup.
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://your-llm-endpoint.example.com/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "demo-api-key")
MODEL_NAME = os.getenv("MODEL_NAME", "demo-llm-model")

BOM_INPUT_PATH = ROOT / "source" / "sample_bom.xlsx"
PLM_INPUT_PATH = ROOT / "source" / "sample_plm_part_list.xlsx"
PLM_INDEX_PATH = ROOT / "output" / "plm_index.pkl"

TOP_N_PER_GROUP = int(os.getenv("TOP_N_PER_GROUP", "10"))
TOKEN_EXPAND_PATH = ROOT / "dict" / "token_expand.csv"
TOKEN_EXCLUDE_PATH = ROOT / "dict" / "token_exclude.csv"

MAPPING_RESULT_PATH = ROOT / "output" / "mapping_result.xlsx"
REVIEW_NEEDED_PATH = ROOT / "output" / "review_needed.xlsx"
LLM_LOG_PATH = ROOT / "output" / "llm_calls.log"
