# -*- coding: utf-8 -*-
"""
Knowledge Base Adaptive Chunking Strategy (自適應知識庫切分策略)

1. 短文件自適應合併 (Short Documents Adaptive Single-Chunk):
   - 當文件總長度（Token 數）小於等於指定的 max_tokens (預設 1024) 時，不進行任何標題拆分，直接保留整篇文件為單一 Chunk。
   - 優點：保留完整的上下文，避免 FAQ 與政策類型短文件因標題過多而將「中繼資料 (Metadata)」與「解決方案 (Solution)」拆開，進而大幅提昇 dense embedding 的相似度分數與檢索完整性。

2. 長文件標題階層拆分 (Long Documents Header-based Splitting):
   - 當文件總長度大於 max_tokens 時，會依據 Markdown 標題層級 (H1 ~ H6) 對文件進行區段拆分。
   - 每個拆分出來的 Chunk 會自動加上標題路徑首碼 (例如 "H1 > H2\n\n")，在保留區域內容時依然維持整體的結構脈絡。

3. 小型 Metadata Section 合併 (Metadata Section Merging):
   - 切分後若某個 section 的內容 token 數小於 METADATA_MERGE_THRESHOLD（預設 200），
     視為純 metadata 區塊（如 Category/Tags 標頭），自動合併至下一個 section。
   - 解決問題：H1 metadata chunk（只含 Category/Tags）的 embedding 相似度高於實際內容 chunk，
     導致搜尋結果只返回 title + tag 而非規格或解決方案。
"""

import re
import tiktoken
from typing import List, Dict, Any
from bs4 import BeautifulSoup


def chunk_markdown(text: str, max_tokens: int = 1024) -> List[Dict[str, Any]]:
    """
    Chunk markdown text into segments with context prefix.

    Args:
        text: Input markdown text
        max_tokens: Maximum tokens per chunk

    Returns:
        List of chunks with index and text
    """
    # 移除夾雜的龐大 HTML 與 CSS 樣式，只保留 Markdown 與文字來計算 Tokens
    text = BeautifulSoup(text, "html.parser").get_text()

    # Initialize tiktoken encoder
    try:
        encoding = tiktoken.get_encoding("cl100k_base")
    except Exception:
        encoding = tiktoken.encoding_for_model("gpt-4")

    # If the entire document fits within a single chunk, do not split it by headers.
    # This preserves local context and solves the fragmented metadata/solution issue for short FAQ pages.
    total_tokens = len(encoding.encode(text))
    if total_tokens <= max_tokens:
        return [{"chunk_index": 0, "chunk_text": text.strip()}]

    # Regex to identify headers (Limit to H1 and H2 only to prevent over-fragmentation of model specifications)
    header_pattern = re.compile(r"^(#{1,2})\s+(.*)$", re.MULTILINE)

    # Find all header positions
    headers = list(header_pattern.finditer(text))

    # Split text into sections based on headers
    sections = []
    last_pos = 0
    current_headers = [""] * 7  # To track current H1, H2, ... H6

    if not headers:
        # No headers found, treat as one single section
        sections.append({"header_path": "", "content": text})
    else:
        # Handle text before the first header
        if headers[0].start() > 0:
            sections.append(
                {"header_path": "", "content": text[: headers[0].start()].strip()}
            )

        for i, match in enumerate(headers):
            level = len(match.group(1))
            title = match.group(2).strip()

            # Update current header path
            current_headers[level] = title
            # Clear lower level headers
            for j in range(level + 1, 7):
                current_headers[j] = ""

            # Construct header path string (e.g., "H1 > H2")
            path_parts = [h for h in current_headers[1 : level + 1] if h]
            header_path = " > ".join(path_parts)

            # Get content until next header or end of text
            start_pos = match.end()
            end_pos = headers[i + 1].start() if i + 1 < len(headers) else len(text)
            content = text[start_pos:end_pos].strip()

            if content:
                sections.append({"header_path": header_path, "content": content})

    # Merge small sections (metadata-only blocks like Category/Tags) into the following section.
    # Prevents the H1 metadata chunk from outscoring the actual content chunk in dense search.
    METADATA_MERGE_THRESHOLD = 200
    merged_sections = []
    i = 0
    while i < len(sections):
        sec = sections[i]
        sec_tokens = len(encoding.encode(sec["content"]))
        if sec_tokens < METADATA_MERGE_THRESHOLD and i + 1 < len(sections):
            next_sec = sections[i + 1]
            merged_sections.append({
                "header_path": next_sec["header_path"],
                "content": sec["content"] + "\n\n" + next_sec["content"],
            })
            i += 2
        else:
            merged_sections.append(sec)
            i += 1
    sections = merged_sections

    chunks = []
    chunk_index = 0

    for section in sections:
        header_path = section["header_path"]
        content = section["content"]

        # Prepare context prefix
        prefix = f"{header_path}\n\n" if header_path else ""
        prefix_tokens = len(encoding.encode(prefix))

        # Check if entire section (with prefix) fits in one chunk
        content_tokens = encoding.encode(content)
        total_tokens = prefix_tokens + len(content_tokens)

        if total_tokens <= max_tokens:
            chunks.append(
                {"chunk_index": chunk_index, "chunk_text": f"{prefix}{content}"}
            )
            chunk_index += 1
        else:
            # Need to split the content
            available_tokens = max_tokens - prefix_tokens
            # Ensure we have at least some room for content
            if available_tokens <= 0:
                # Header path is too long? Just use content and hope for the best
                available_tokens = max_tokens // 2
                prefix = ""

            # Split content using token-based window
            for j in range(0, len(content_tokens), available_tokens):
                # Take slice of tokens
                chunk_tokens = content_tokens[j : j + available_tokens]
                chunk_content = encoding.decode(chunk_tokens)

                chunks.append(
                    {"chunk_index": chunk_index, "chunk_text": f"{prefix}{chunk_content}"}
                )
                chunk_index += 1

    return chunks
