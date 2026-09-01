from __future__ import annotations

import io
import pickle
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from . import config
from .integrations.llm_client import make_llm_client
from .stages.input.bom_cleaner import clean_bom
from .stages.mapping.part_mapper import map_parts
from .stages.normalization.plm_indexer import build_index
from .stages.normalization.tokenizer import load_token_exclude, load_token_expand, tokenize_bom


@dataclass
class PipelineArtifacts:
    clean_df: pd.DataFrame
    normalized_df: pd.DataFrame
    mapping_df: pd.DataFrame
    grouped_mapping_df: pd.DataFrame
    review_df: pd.DataFrame
    comparison_df: pd.DataFrame
    spec_cols: list[str]


def load_plm_index(index_path: Path | None = None):
    index_path = index_path or config.PLM_INDEX_PATH
    if not index_path.exists():
        build_index()
    with open(index_path, "rb") as fh:
        return pickle.load(fh)


def build_normalized_preview(clean_df: pd.DataFrame, spec_cols: list[str]):
    token_exclude = load_token_exclude(config.TOKEN_EXCLUDE_PATH)
    token_expand = load_token_expand(config.TOKEN_EXPAND_PATH)

    rows = []
    for _, row in clean_df.iterrows():
        spec_vals = [row.get(c) for c in spec_cols]
        tokens = sorted(
            tokenize_bom(
                row.get("SpecSummary", ""),
                spec_vals,
                token_exclude=token_exclude,
                token_expand=token_expand,
            )
        )
        rows.append(
            {
                "Location": row.get("Location", ""),
                "SpecSummary": row.get("SpecSummary", ""),
                "NormalizedTokens": ", ".join(tokens),
                "TokenCount": len(tokens),
            }
        )
    return pd.DataFrame(rows)


def run_pipeline(
    bom_file_path: str | Path,
    *,
    llm_base_url: str | None = None,
    llm_api_key: str | None = None,
    model_name: str | None = None,
    top_n: int | None = None,
    log_path: str | Path | None = None,
):
    clean_df, bom_review, spec_cols = clean_bom(bom_file_path)
    normalized_df = build_normalized_preview(clean_df, spec_cols)

    if clean_df.empty:
        review_df = pd.DataFrame(
            bom_review, columns=["Location", "SpecSummary", "Issue Type", "Original Value"]
        )
        empty_mapping = pd.DataFrame()
        empty_comparison = pd.DataFrame()
        return PipelineArtifacts(
            clean_df=clean_df,
            normalized_df=normalized_df,
            mapping_df=empty_mapping,
            grouped_mapping_df=empty_mapping,
            review_df=review_df,
            comparison_df=empty_comparison,
            spec_cols=spec_cols,
        )

    plm_index = load_plm_index()
    token_exclude = load_token_exclude(config.TOKEN_EXCLUDE_PATH)
    token_expand = load_token_expand(config.TOKEN_EXPAND_PATH)
    client = make_llm_client(llm_base_url or config.LLM_BASE_URL, llm_api_key or config.LLM_API_KEY)

    result_df, map_review = map_parts(
        clean_df,
        plm_index,
        client,
        model_name or config.MODEL_NAME,
        top_n=top_n or config.TOP_N_PER_GROUP,
        token_exclude=token_exclude,
        token_expand=token_expand,
        log_path=str(log_path) if log_path else None,
    )

    review_df = pd.DataFrame(
        bom_review + map_review,
        columns=["Location", "SpecSummary", "Issue Type", "Original Value"],
    )

    grouped_mapping_df = build_grouped_mapping_view(result_df)
    comparison_df = build_comparison_view(grouped_mapping_df)
    return PipelineArtifacts(
        clean_df=clean_df,
        normalized_df=normalized_df,
        mapping_df=result_df,
        grouped_mapping_df=grouped_mapping_df,
        review_df=review_df,
        comparison_df=comparison_df,
        spec_cols=spec_cols,
    )


def build_grouped_mapping_view(mapping_df: pd.DataFrame):
    if mapping_df.empty:
        return pd.DataFrame()

    group_cols = [col for col in mapping_df.columns if col != "Location"]
    if not group_cols:
        return mapping_df.copy()

    rows = []
    for key, group in mapping_df.groupby(group_cols, dropna=False, sort=False):
        if len(group_cols) == 1:
            key = (key,)
        row = dict(zip(group_cols, key))
        locations = [str(loc).strip() for loc in group["Location"] if str(loc).strip()]
        row["Location"] = ",".join(locations)
        row["Quantity"] = len(locations) if locations else len(group)
        rows.append(row)

    grouped_df = pd.DataFrame(rows)
    leading_cols = [col for col in ["Location", "Quantity", "SpecSummary"] if col in grouped_df.columns]
    ordered = leading_cols + [col for col in grouped_df.columns if col not in leading_cols]
    return grouped_df[ordered]


def build_comparison_view(mapping_df: pd.DataFrame):
    if mapping_df.empty:
        return pd.DataFrame()

    view = mapping_df.copy()
    cols = [
        "Location",
        "SpecSummary",
        "Active_1_PN",
        "Active_1_Desc",
        "Active_1_Conf",
        "Active_1_Diff",
        "Inactive_1_PN",
        "Inactive_1_Desc",
        "Inactive_1_Conf",
        "Inactive_1_Diff",
    ]
    existing = [c for c in cols if c in view.columns]
    view = view[existing].copy()
    view = view.rename(
        columns={
            "Active_1_PN": "Recommended_Active_PN",
            "Active_1_Desc": "Recommended_Active_Desc",
            "Active_1_Conf": "Recommended_Active_Conf",
            "Active_1_Diff": "Recommended_Active_Diff",
            "Inactive_1_PN": "Alternative_Inactive_PN",
            "Inactive_1_Desc": "Alternative_Inactive_Desc",
            "Inactive_1_Conf": "Alternative_Inactive_Conf",
            "Inactive_1_Diff": "Alternative_Inactive_Diff",
        }
    )
    return view


def dataframe_to_csv_bytes(df: pd.DataFrame):
    output = io.StringIO()
    df.to_csv(output, index=False, encoding="utf-8")
    return output.getvalue().encode("utf-8")


def persist_uploaded_file(uploaded_file, suffix: str | None = None):
    suffix = suffix or Path(uploaded_file.name).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getbuffer())
        return Path(tmp.name)
