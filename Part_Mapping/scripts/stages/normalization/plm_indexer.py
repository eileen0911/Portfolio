import pickle
from pathlib import Path
import sys

import pandas as pd

try:
    from .tokenizer import tokenize_plm, load_token_exclude
    from ... import config
except ImportError:  # pragma: no cover - supports direct script execution
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from scripts import config
    from scripts.stages.normalization.tokenizer import tokenize_plm, load_token_exclude

PLM_INPUT_PATH = config.PLM_INPUT_PATH
TOKEN_EXCLUDE_PATH = config.TOKEN_EXCLUDE_PATH
OUTPUT_PATH = config.PLM_INDEX_PATH

INACTIVE_STATUSES = {"EOP (停用)", "EOP (停產)", "EOL (停產)", "DNI (禁用)"}
INVALID_DESC_KEYWORDS = ["此料已在ERP不可使用"]

# Tie-breaking within active group: lower number = higher priority
STATUS_PRIORITY = {
    'Production': 0,
    'Prototype': 1,
    'Preliminary': 2,
}


def build_index():
    config.PLM_INDEX_PATH.parent.mkdir(exist_ok=True)
    token_exclude = load_token_exclude(TOKEN_EXCLUDE_PATH)

    df = pd.read_excel(PLM_INPUT_PATH)
    df.columns = ['part_number', 'desc_spec', 'status', 'version', 'part_type']

    # 排除含特定文字的無效料件
    invalid_kw = '|'.join(INVALID_DESC_KEYWORDS)
    invalid_mask = df['desc_spec'].astype(str).str.contains(invalid_kw, na=False)
    removed = invalid_mask.sum()
    if removed:
        print(f"Removing {removed} entries with invalid desc_spec content")
    df = df[~invalid_mask].copy()

    active_df = df[~df['status'].isin(INACTIVE_STATUSES)].copy()
    inactive_df = df[df['status'].isin(INACTIVE_STATUSES)].copy()
    print(f"Total PLM rows: {len(df)}, active: {len(active_df)}, inactive: {len(inactive_df)}")

    def build_group(group_df):
        index = {}
        for _, row in group_df.iterrows():
            pn = str(row['part_number']).strip()
            desc = str(row['desc_spec']) if pd.notna(row['desc_spec']) else ''
            status = str(row['status']).strip()
            index[pn] = (tokenize_plm(desc, token_exclude), desc, status)
        return index

    active_index = build_group(active_df)
    inactive_index = build_group(inactive_df)

    with open(OUTPUT_PATH, 'wb') as f:
        pickle.dump({'active': active_index, 'inactive': inactive_index}, f)

    print(f"Saved: active={len(active_index)}, inactive={len(inactive_index)} entries -> {OUTPUT_PATH}")
    return active_index, inactive_index


if __name__ == '__main__':
    build_index()
