from __future__ import annotations

import threading
import tempfile
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from scripts import config
from scripts.integrations.llm_client import make_llm_client
from scripts.pipeline import (
    PipelineArtifacts,
    build_comparison_view,
    build_grouped_mapping_view,
    build_normalized_preview,
    dataframe_to_csv_bytes,
    load_plm_index,
    persist_uploaded_file,
)
from scripts.stages.input.bom_cleaner import clean_bom
from scripts.stages.input.input_validator import validate_bom_template
from scripts.stages.input.raw_transformers import AMD_RAW_BOM_FORMAT, RAW_BOM_FORMAT_OPTIONS, RAW_BOM_TRANSFORMERS
from scripts.stages.mapping.part_mapper import map_parts
from scripts.stages.normalization.tokenizer import load_token_exclude, load_token_expand, tokenize_bom

st.set_page_config(page_title="零件料號 Mapping 流程", page_icon="Package", layout="wide")


WORKFLOW_STAGES = [
    ("template", "輸入模板", "整理標準 BOM 欄位"),
    ("upload", "上傳 BOM", "選擇整理後的 Excel 檔"),
    ("validate", "BOM 檢查", "轉換與檢查模板欄位與資料規則"),
    ("clean", "清理 BOM", "排除 N 列並拆分 Location"),
    ("normalize", "規格正規化", "建立可搜尋的 token 預覽"),
    ("map", "料號 Mapping", "評分候選料號並呼叫 LLM"),
    ("results", "檢視與匯出", "檢查結果並下載 CSV"),
]


SESSION_KEYS = (
    "artifacts",
    "bom_review",
    "log_file",
    "mapping_requested",
    "mapping_running",
    "transform_summary",
    "upload_key",
    "uploaded_path",
    "validation_result",
)

MAPPING_SECONDS_PER_CALL = 15
MAPPING_PROGRESS_REFRESH_SECONDS = 5
UPLOAD_WIDGET_KEY_STATE = "upload_widget_key"

SPEC_DISPLAY_COLUMN_LABELS = {
    "Spec": "Spec.1",
    "Spec.1": "Spec.2",
    "Spec.2": "Spec.3",
    "Spec.3": "Spec.4",
}

DISPLAY_COLUMN_LABELS = {
    "Row": "列",
    "Column": "欄位",
    "Issue": "問題",
    "Value": "值",
    "Stage": "階段",
    "File": "檔案",
    "Rows": "列數",
}

DISPLAY_VALUE_LABELS = {
    "Header": "標題列",
    "Missing required column": "缺少必要欄位",
    "SpecSummary or at least one Spec column is required for mapping rows": (
        "進入 Mapping 的列必須有 SpecSummary 或至少一個 Spec 欄位"
    ),
    "Use commas to separate multiple locations": "多個 Location 請使用逗號分隔",
}


def _metric_block(label, value):
    st.metric(label, value)


def _clear_workflow_state():
    for key in SESSION_KEYS:
        st.session_state.pop(key, None)


def _reset_workflow_state(*, clear_upload: bool = False):
    old_upload_widget_key = st.session_state.get(UPLOAD_WIDGET_KEY_STATE)
    _clear_workflow_state()
    if clear_upload:
        if old_upload_widget_key:
            st.session_state.pop(old_upload_widget_key, None)
        st.session_state[UPLOAD_WIDGET_KEY_STATE] = f"bom_upload_{time.time_ns()}"


def _render_workflow(current_key: str):
    current_idx = next(
        (idx for idx, (key, _, _) in enumerate(WORKFLOW_STAGES) if key == current_key),
        0,
    )
    rows = []
    for idx, (key, label, description) in enumerate(WORKFLOW_STAGES):
        if idx < current_idx:
            state = "done"
            marker = "完成"
        elif idx == current_idx:
            state = "current"
            marker = "目前"
        else:
            state = "todo"
            marker = f"{idx + 1}"
        rows.append(
            f'<div class="workflow-step workflow-{state}">'
            f'<div class="workflow-marker">{marker}</div>'
            f'<div class="workflow-copy">'
            f'<div class="workflow-label">{label}</div>'
            f'<div class="workflow-desc">{description}</div>'
            f'</div></div>'
        )
    html = """
<style>
.workflow-step {
    display: flex;
    gap: 0.65rem;
    align-items: flex-start;
    padding: 0.55rem 0.45rem;
    border-left: 3px solid #d6d9df;
    margin: 0.15rem 0 0.15rem 0.35rem;
}
.workflow-current {
    border-left-color: #ff4b4b;
    background: rgba(255, 75, 75, 0.10);
    border-radius: 6px;
}
.workflow-done {
    border-left-color: #2e7d32;
    opacity: 0.82;
}
.workflow-todo {
    color: #69707d;
}
.workflow-marker {
    min-width: 2.1rem;
    height: 1.35rem;
    border-radius: 999px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 0.68rem;
    font-weight: 700;
    background: #eef0f3;
    color: #333842;
}
.workflow-current .workflow-marker {
    background: #ff4b4b;
    color: white;
}
.workflow-done .workflow-marker {
    background: #2e7d32;
    color: white;
}
.workflow-label {
    font-weight: 700;
    line-height: 1.15;
}
.workflow-desc {
    font-size: 0.78rem;
    color: #69707d;
    line-height: 1.25;
    margin-top: 0.15rem;
}
</style>
""" + "\n".join(rows)
    st.markdown(html, unsafe_allow_html=True)


def _test_llm_connection():
    client = make_llm_client(config.LLM_BASE_URL, config.LLM_API_KEY)
    resp = client.chat.completions.create(
        model=config.MODEL_NAME,
        messages=[
            {"role": "system", "content": "Return only OK."},
            {"role": "user", "content": "ping"},
        ],
        temperature=0.0,
        max_tokens=8,
    )
    return resp.choices[0].message.content or ""


def _make_arrow_safe_df(df: pd.DataFrame) -> pd.DataFrame:
    safe_df = df.copy()
    for col in safe_df.columns:
        if safe_df[col].dtype == "object":
            safe_df[col] = safe_df[col].map(_display_value)
    for col in ("Row", "Issue"):
        if col in safe_df.columns:
            safe_df[col] = safe_df[col].map(lambda value: DISPLAY_VALUE_LABELS.get(value, value))
    safe_df = safe_df.rename(columns=_display_column_labels(safe_df))
    return safe_df


def _display_column_labels(df: pd.DataFrame) -> dict[str, str]:
    labels = dict(DISPLAY_COLUMN_LABELS)
    if "Spec.4" not in df.columns:
        labels.update(SPEC_DISPLAY_COLUMN_LABELS)
    return labels


def _display_value(value):
    if pd.isna(value):
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _display_dataframe(df: pd.DataFrame, *, height: int | None = None, hide_index: bool | None = None):
    kwargs = {"width": "stretch"}
    if height is not None:
        kwargs["height"] = height
    if hide_index is not None:
        kwargs["hide_index"] = hide_index
    st.dataframe(_make_arrow_safe_df(df), **kwargs)


def _persist_transformed_bom(df: pd.DataFrame) -> Path:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        path = Path(tmp.name)
    df.to_excel(path, index=False)
    return path


def _format_duration(seconds: float | int) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours} 小時 {minutes} 分"
    if minutes:
        return f"{minutes} 分 {seconds} 秒"
    return f"{seconds} 秒"


def _estimate_mapping_call_count(clean_df, spec_cols, token_exclude, token_expand):
    unique_sets = set()
    for _, row in clean_df.iterrows():
        spec_vals = [row.get(c) for c in spec_cols]
        unique_sets.add(
            tokenize_bom(
                row.get("SpecSummary", ""),
                spec_vals,
                token_exclude=token_exclude,
                token_expand=token_expand,
            )
        )
    return len(unique_sets)


def _render_mapping_progress(progress_bar, status_slot, progress_state, elapsed_seconds):
    total = max(0, int(progress_state.get("total") or 0))
    completed = max(0, int(progress_state.get("completed") or 0))
    ratio = completed / total if total else 0
    progress_bar.progress(min(ratio, 1.0))

    estimated_total_seconds = total * MAPPING_SECONDS_PER_CALL
    current_spec = str(progress_state.get("spec_summary") or "")
    current_spec = current_spec[:90] + ("..." if len(current_spec) > 90 else "")
    status_map = {
        "Preparing LLM mapping": "準備 LLM Mapping",
        "Mapping": "Mapping 中",
        "Completed": "已完成",
    }
    status = status_map.get(progress_state.get("status"), progress_state.get("status") or "Mapping 中")

    status_slot.info(
        f"{status}: [{completed}/{total}] | "
        f"預估總時間: {_format_duration(estimated_total_seconds)}"
        + (f"\n\n目前規格: {current_spec}" if current_spec else "")
    )


def _empty_review_df():
    return pd.DataFrame(columns=["Location", "SpecSummary", "Issue Type", "Original Value"])


def _validation_issue_text(issue: str) -> str:
    return DISPLAY_VALUE_LABELS.get(str(issue), str(issue))


def _render_validation_summary(validation_result):
    errors = validation_result.errors
    warnings = validation_result.warnings

    if not errors.empty:
        st.error("請先修正下列錯誤後再繼續流程。")
        for _, row in errors.head(8).iterrows():
            st.write(
                f"- 列: `{_validation_issue_text(row.get('Row', ''))}` | "
                f"欄位: `{row.get('Column', '')}` | "
                f"問題: {_validation_issue_text(row.get('Issue', ''))}"
            )
        if len(errors) > 8:
            st.write(f"- 另有 {len(errors) - 8} 個錯誤，請查看下方完整明細。")

    if not warnings.empty:
        st.warning("以下警告不會阻擋流程，但建議確認。")
        warning_summary = (
            warnings.groupby(["Column", "Issue"], dropna=False)
            .size()
            .reset_index(name="Count")
            .rename(columns={"Count": "Rows"})
        )
        _display_dataframe(warning_summary, hide_index=True, height=180)


def _make_clean_artifacts(clean_df, bom_review, spec_cols):
    normalized_df = build_normalized_preview(clean_df, spec_cols)
    review_df = pd.DataFrame(
        bom_review,
        columns=["Location", "SpecSummary", "Issue Type", "Original Value"],
    )
    return PipelineArtifacts(
        clean_df=clean_df,
        normalized_df=normalized_df,
        mapping_df=pd.DataFrame(),
        grouped_mapping_df=pd.DataFrame(),
        review_df=review_df,
        comparison_df=pd.DataFrame(),
        spec_cols=spec_cols,
    )


def _render_outputs(artifacts, log_file=None):
    grouped_mapping_df = getattr(artifacts, "grouped_mapping_df", artifacts.mapping_df)
    csv_outputs = {
        "cleaned_bom.csv": dataframe_to_csv_bytes(artifacts.clean_df),
        "normalized_bom.csv": dataframe_to_csv_bytes(artifacts.normalized_df),
        "mapping_result.csv": dataframe_to_csv_bytes(grouped_mapping_df),
        "comparison_view.csv": dataframe_to_csv_bytes(artifacts.comparison_df),
        "review_needed.csv": dataframe_to_csv_bytes(artifacts.review_df),
    }

    clean_count = len(artifacts.clean_df)
    review_count = len(artifacts.review_df)
    mapping_count = len(grouped_mapping_df)
    mapped_location_count = len(artifacts.mapping_df)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        _metric_block("清理後列數", clean_count)
    with col2:
        _metric_block("Mapping 群組數", mapping_count)
    with col3:
        _metric_block("Mapping Location 數", mapped_location_count)
    with col4:
        _metric_block("待確認項目", review_count)

    tab_clean, tab_norm, tab_map, tab_compare, tab_review, tab_export = st.tabs(
        [
            "清理後 BOM",
            "正規化 BOM",
            "Mapping 結果",
            "比較檢視",
            "待確認",
            "匯出",
        ]
    )

    with tab_clean:
        st.download_button(
            "下載 cleaned_bom.csv",
            data=csv_outputs["cleaned_bom.csv"],
            file_name="cleaned_bom.csv",
            mime="text/csv",
        )
        _display_dataframe(artifacts.clean_df, height=620)

    with tab_norm:
        st.download_button(
            "下載 normalized_bom.csv",
            data=csv_outputs["normalized_bom.csv"],
            file_name="normalized_bom.csv",
            mime="text/csv",
        )
        _display_dataframe(artifacts.normalized_df, height=620)

    with tab_map:
        st.download_button(
            "下載 mapping_result.csv",
            data=csv_outputs["mapping_result.csv"],
            file_name="mapping_result.csv",
            mime="text/csv",
        )
        if grouped_mapping_df.empty:
            st.info("尚未執行 Mapping。")
        else:
            _display_dataframe(grouped_mapping_df, height=620)

    with tab_compare:
        st.download_button(
            "下載 comparison_view.csv",
            data=csv_outputs["comparison_view.csv"],
            file_name="comparison_view.csv",
            mime="text/csv",
        )
        if artifacts.comparison_df.empty:
            st.info("Mapping 完成後會產生比較檢視。")
        else:
            _display_dataframe(artifacts.comparison_df, height=620)

    with tab_review:
        st.download_button(
            "下載 review_needed.csv",
            data=csv_outputs["review_needed.csv"],
            file_name="review_needed.csv",
            mime="text/csv",
        )
        review_df = artifacts.review_df if not artifacts.review_df.empty else _empty_review_df()
        _display_dataframe(review_df, height=620)

    with tab_export:
        st.write("各階段結果會分別匯出成 CSV 檔。")
        _display_dataframe(
            pd.DataFrame(
                [
                    {"Stage": "清理後 BOM", "File": "cleaned_bom.csv", "Rows": len(artifacts.clean_df)},
                    {"Stage": "正規化 BOM", "File": "normalized_bom.csv", "Rows": len(artifacts.normalized_df)},
                    {"Stage": "Mapping 結果", "File": "mapping_result.csv", "Rows": len(grouped_mapping_df)},
                    {"Stage": "比較檢視", "File": "comparison_view.csv", "Rows": len(artifacts.comparison_df)},
                    {"Stage": "待確認", "File": "review_needed.csv", "Rows": len(artifacts.review_df)},
                ]
            ),
            hide_index=True,
        )

        if log_file and Path(log_file).exists():
            st.download_button(
                "下載 LLM Log",
                data=Path(log_file).read_bytes(),
                file_name="llm_calls.log",
                mime="text/plain",
            )


st.title("零件料號 Mapping 流程")
st.caption("上傳整理後的 BOM，檢查清理與正規化結果，再產生料號 Mapping 與比較檢視。")

with st.sidebar:
    st.subheader("執行設定")
    st.caption(f"版本: `v{config.APP_VERSION}` / Build `{config.APP_BUILD}`")
    st.caption(f"LLM URL: `{config.LLM_BASE_URL}`")
    st.caption(f"模型名稱: `{config.MODEL_NAME}`")
    st.caption(f"Top-N 候選數: `{config.TOP_N_PER_GROUP}`")
    st.caption(f"PLM 來源: `{config.PLM_INPUT_PATH.name}`")
    st.caption(f"PLM Index: `{config.PLM_INDEX_PATH.name}`")
    if st.button("測試 LLM 連線"):
        with st.spinner("正在測試 LLM 連線..."):
            try:
                test_response = _test_llm_connection().strip()
                st.success(f"LLM 連線成功: {test_response or 'OK'}")
            except Exception as exc:
                st.error(f"LLM 連線失敗: {exc}")
    st.divider()
    st.subheader("流程")
    reset_disabled = st.session_state.get("mapping_requested", False) or st.session_state.get("mapping_running", False)
    if st.button("重置流程", disabled=reset_disabled):
        _reset_workflow_state(clear_upload=True)
        st.rerun()
    workflow_slot = st.empty()

if UPLOAD_WIDGET_KEY_STATE not in st.session_state:
    st.session_state[UPLOAD_WIDGET_KEY_STATE] = "bom_upload_0"

uploaded_bom = st.file_uploader(
    "BOM 檔案",
    type=["xls", "xlsx", "csv"],
    key=st.session_state[UPLOAD_WIDGET_KEY_STATE],
)

template_expanded = uploaded_bom is None and "validation_result" not in st.session_state
with st.expander("輸入模板", expanded=template_expanded):
    st.markdown(
        """
上傳前請先將 BOM Excel 整理成下列模板，第一列必須是欄位名稱。

- 欄位名稱: `Spec.1`, `Spec.2`, `Spec.3`, `Spec.4`, `SpecSummary`, `Location`, `PutIntoBOM`
- 所有欄位皆非必填，但至少要有一個Spec
- `PutIntoBOM`: `N`、`DNI`、`DEBUG` 會被排除，其他值都會進入 Mapping
- `Location` 可以為空，適用於沒有 PCB 位置的零件
- 多個 Location 請用逗號分隔，例如 `C1,C2,C3`
"""
    )

    template_demo = pd.DataFrame(
        [
            {
                "Spec.1": "100n",
                "Spec.2": "+/-10%",
                "Spec.3": "25V",
                "Spec.4": "201",
                "SpecSummary": "CAPC, 100NF 25V X5R 0201",
                "Location": "C259,C260,C262",
                "PutIntoBOM": "Y",
            },
            {
                "Spec.1": "10K",
                "Spec.2": "1%",
                "Spec.3": "1/16W",
                "Spec.4": "402",
                "SpecSummary": "RES, 10KOHM 1% 1/16W 0402",
                "Location": "R12,R13",
                "PutIntoBOM": "Y",
            },
            {
                "Spec.1": "2.2u",
                "Spec.2": "+/-20%",
                "Spec.3": "6.3V",
                "Spec.4": "201",
                "SpecSummary": "CAPC, 2.2UF 6.3V X5R 0201",
                "Location": "C17,C18",
                "PutIntoBOM": "N",
            },
            {
                "Spec.1": "25MHz",
                "Spec.2": "30ppm",
                "Spec.3": "20pF",
                "Spec.4": "2.0X1.6mm",
                "SpecSummary": "Crystal,25MHz, 30ppm, 20pF, 2.0X1.6mm, SMT",
                "Location": "Y1,BY1",
                "PutIntoBOM": "Y",
            },
        ]
    )
    _display_dataframe(template_demo, hide_index=True)


if uploaded_bom is None:
    with workflow_slot.container():
        _render_workflow("template")
    st.info("請上傳整理後的 BOM 檔案以開始流程。")
    st.stop()

upload_key = f"{uploaded_bom.name}:{getattr(uploaded_bom, 'size', 0)}"
if st.session_state.get("upload_key") != upload_key:
    _clear_workflow_state()
    st.session_state.upload_key = upload_key

if "validation_result" not in st.session_state:
    with workflow_slot.container():
        _render_workflow("upload")
    bom_format = st.radio(
        "BOM 格式",
        RAW_BOM_FORMAT_OPTIONS,
        horizontal=True,
    )
    if st.button("檢查 BOM", type="primary"):
        with workflow_slot.container():
            _render_workflow("validate")
        with st.spinner("正在檢查 BOM 模板..."):
            uploaded_path = persist_uploaded_file(uploaded_bom)
            transformer = RAW_BOM_TRANSFORMERS[bom_format]
            if transformer:
                transformed_df, transform_warnings = transformer(uploaded_path)
                uploaded_path = _persist_transformed_bom(transformed_df)
                st.session_state.transform_summary = {
                    "format": bom_format,
                    "rows": len(transformed_df),
                    "warnings": transform_warnings,
                }
            else:
                st.session_state.transform_summary = {
                    "format": bom_format,
                    "rows": None,
                    "warnings": [],
                }
            st.session_state.uploaded_path = uploaded_path
            st.session_state.validation_result = validate_bom_template(uploaded_path)
        st.rerun()
    st.stop()

validation_result = st.session_state.validation_result
with workflow_slot.container():
    _render_workflow("validate" if not validation_result.valid else "clean")

if not validation_result.valid:
    st.error(f"BOM 檢查失敗: {len(validation_result.errors)} 個錯誤，{len(validation_result.warnings)} 個警告。")
    _render_validation_summary(validation_result)
    with st.expander("BOM 檢查明細", expanded=True):
        if not validation_result.errors.empty:
            st.subheader("錯誤")
        _display_dataframe(validation_result.errors, hide_index=True, height=320)
        if not validation_result.warnings.empty:
            st.warning("檢查警告")
            _display_dataframe(validation_result.warnings, hide_index=True, height=260)
    with st.expander("上傳檔案預覽", expanded=False):
        _display_dataframe(validation_result.preview_df, height=360)
    if st.button("測試 LLM 連線"):
        _clear_workflow_state()
        st.rerun()
    st.stop()

transform_summary = st.session_state.get("transform_summary")
standard_tab, validation_tab = st.tabs(["標準輸入模板 BOM", "BOM 檢查"])
with standard_tab:
    if transform_summary and transform_summary.get("format") == AMD_RAW_BOM_FORMAT:
        st.info(f"AMD Raw BOM 已轉換為標準輸入模板: {transform_summary.get('rows', 0)} 列。")
    _display_dataframe(validation_result.preview_df, hide_index=True, height=360)

with validation_tab:
    st.success(f"BOM 檢查通過: {len(validation_result.warnings)} 個警告。")
    if transform_summary and transform_summary.get("warnings"):
        with st.expander("Raw BOM 轉換警告", expanded=True):
            for warning in transform_summary["warnings"]:
                st.write(f"- {warning}")
    if not validation_result.warnings.empty:
        with st.expander("BOM 檢查明細", expanded=True):
            _display_dataframe(validation_result.warnings, hide_index=True, height=260)

if "artifacts" not in st.session_state:
    if st.button("清理並正規化", type="primary"):
        with workflow_slot.container():
            _render_workflow("clean")
        with st.spinner("正在清理 BOM 並建立正規化 token 預覽..."):
            uploaded_path = st.session_state.uploaded_path
            clean_df, bom_review, spec_cols = clean_bom(uploaded_path)
            artifacts = _make_clean_artifacts(clean_df, bom_review, spec_cols)
        st.session_state.artifacts = artifacts
        st.session_state.bom_review = bom_review
        with workflow_slot.container():
            _render_workflow("normalize")
        st.rerun()
    st.stop()

artifacts = st.session_state.artifacts
mapping_done = not artifacts.mapping_df.empty
with workflow_slot.container():
    _render_workflow("results" if mapping_done else "normalize")

if not mapping_done:
    st.success(f"清理與正規化完成: {len(artifacts.clean_df)} 列清理後資料，{len(artifacts.normalized_df)} 列正規化資料。")
    with st.expander("清理 / 正規化階段摘要", expanded=True):
        st.write("執行 Mapping 前，請先檢查下方的清理後 BOM 與正規化 BOM。")
        st.markdown(
            """
            正規化規則摘要：
            - 將文字轉為大寫、移除前後空白，並把底線 `_` 轉為連字號 `-`。
            - 以空白、逗號、冒號作為 token 分隔符；`ESR:10M` 會拆成 `ESR` 與 `10M`。
            - 斜線 `/` 通常會拆分 token，但 `+/-10%`、`S/C`、`M/C` 這類短字母組合會保留。
            - 電容單位統一為 `UF`，例如 `100NF` 轉為 `0.1UF`、`100PF` 轉為 `0.0001UF`。
            - 電阻常見寫法會統一，例如 `4R7` 轉為 `4.7OHM`、`10R` 轉為 `10OHM`。
            - 電感 `NH` 會轉為 `UH`，常見 3 碼 package code 會補成 4 碼，例如 `603` 轉為 `0603`。
            - 正規化後會套用排除字典與展開字典，最後以去重後的 token set 作為 Mapping 比對基礎。
            """
        )
        st.write("如果結果不符合預期，請先修改輸入模板後再重新上傳，或與管理員反饋需增加的正規化規則。")
    mapping_requested = st.session_state.get("mapping_requested", False)
    mapping_running = st.session_state.get("mapping_running", False)
    run_mapping = st.button(
        "執行 Mapping",
        type="primary",
        disabled=artifacts.clean_df.empty or mapping_requested or mapping_running,
    )
    if artifacts.clean_df.empty:
        st.warning("沒有可進行 Mapping 的清理後資料。")
    if run_mapping and not mapping_requested and not mapping_running:
        st.session_state.mapping_requested = True
        st.session_state.mapping_running = True
        st.rerun()
    if mapping_requested and mapping_running:
        st.session_state.mapping_running = True
        with workflow_slot.container():
            _render_workflow("map")
        log_file = Path(tempfile.gettempdir()) / "part_mapping_llm_calls.log"

        try:
            plm_index = load_plm_index()
            token_exclude = load_token_exclude(config.TOKEN_EXCLUDE_PATH)
            token_expand = load_token_expand(config.TOKEN_EXPAND_PATH)
            estimated_total = _estimate_mapping_call_count(
                artifacts.clean_df,
                artifacts.spec_cols,
                token_exclude,
                token_expand,
            )
        except Exception as exc:  # noqa: BLE001 - surface setup failures in UI
            st.session_state.mapping_requested = False
            st.session_state.mapping_running = False
            st.error(f"Mapping 前置作業失敗: {exc}")
            st.stop()

        try:
            with st.spinner("正在測試 LLM 連線..."):
                _test_llm_connection()
        except Exception as exc:  # noqa: BLE001 - keep mapping from starting on LLM failures
            st.session_state.mapping_requested = False
            st.session_state.mapping_running = False
            st.error(f"LLM 連線失敗，已停止執行 Mapping，請通知管理員。 {exc}")
            st.stop()

        progress_bar = st.progress(0)
        progress_status = st.empty()
        result_holder = {}
        progress_lock = threading.Lock()

        progress_state = {
            "completed": 0,
            "total": estimated_total,
            "status": "Preparing LLM mapping",
            "spec_summary": "",
        }

        def update_progress(payload):
            with progress_lock:
                progress_state.update(payload)

        def run_mapping_worker():
            try:
                client = make_llm_client(config.LLM_BASE_URL, config.LLM_API_KEY)
                result_holder["result"] = map_parts(
                    artifacts.clean_df,
                    plm_index,
                    client,
                    config.MODEL_NAME,
                    top_n=config.TOP_N_PER_GROUP,
                    token_exclude=token_exclude,
                    token_expand=token_expand,
                    log_path=str(log_file),
                    progress_callback=update_progress,
                )
            except Exception as exc:  # noqa: BLE001 - surface mapping failures in UI
                result_holder["error"] = exc

        worker = threading.Thread(target=run_mapping_worker, daemon=True)
        worker.start()
        started_at = time.time()

        while worker.is_alive():
            with progress_lock:
                snapshot = dict(progress_state)
            _render_mapping_progress(
                progress_bar,
                progress_status,
                snapshot,
                elapsed_seconds=time.time() - started_at,
            )
            time.sleep(MAPPING_PROGRESS_REFRESH_SECONDS)

        worker.join()
        with progress_lock:
            snapshot = dict(progress_state)
        _render_mapping_progress(
            progress_bar,
            progress_status,
            snapshot,
            elapsed_seconds=time.time() - started_at,
        )

        st.session_state.mapping_running = False
        if "error" in result_holder:
            st.session_state.mapping_requested = False
            st.error(f"Mapping 失敗: {result_holder['error']}")
            st.stop()

        with st.spinner("正在整理 Mapping 輸出..."):
            result_df, map_review = result_holder["result"]
            bom_review = st.session_state.get("bom_review", [])
            review_df = pd.DataFrame(
                bom_review + map_review,
                columns=["Location", "SpecSummary", "Issue Type", "Original Value"],
            )
            grouped_mapping_df = build_grouped_mapping_view(result_df)
            st.session_state.artifacts = PipelineArtifacts(
                clean_df=artifacts.clean_df,
                normalized_df=artifacts.normalized_df,
                mapping_df=result_df,
                grouped_mapping_df=grouped_mapping_df,
                review_df=review_df,
                comparison_df=build_comparison_view(grouped_mapping_df),
                spec_cols=artifacts.spec_cols,
            )
            st.session_state.log_file = log_file
            st.session_state.mapping_requested = False
            st.session_state.mapping_running = False
        st.rerun()

_render_outputs(st.session_state.artifacts, st.session_state.get("log_file"))
