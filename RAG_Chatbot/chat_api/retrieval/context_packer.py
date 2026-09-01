from typing import Any

import tiktoken

from chat_api.config import Settings
from chat_api.models import ChatIntake, Source
from chat_api.retrieval.product_matcher import filter_exact_product_sources


class SourcePacker:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._encoding = self._token_encoder()

    def pack(
        self,
        question: str,
        candidate_sources: list[Source],
        intake: ChatIntake | None = None,
        exact_page_ids: list[int | str] | None = None,
    ) -> list[Source]:
        exact_page_keys = {str(page_id) for page_id in exact_page_ids or []}
        candidate_sources = filter_exact_product_sources(
            question,
            candidate_sources,
            intake.intent if intake else None,
        )
        grouped: dict[str, list[Source]] = {}
        for source in candidate_sources:
            grouped.setdefault(str(source.page_id), []).append(source)

        pages = []
        for page_id, chunks in grouped.items():
            sorted_chunks = self._sort_chunks(page_id, chunks, exact_page_keys)
            pages.append(
                {
                    "page_id": page_id,
                    "score": sorted_chunks[0].score,
                    "chunks": sorted_chunks,
                }
            )

        selected_pages = sorted(pages, key=lambda page: page["score"], reverse=True)[
            : self._settings.retrieval_top_k
        ]
        packed: list[Source] = []
        selected_counts: dict[str, int] = {}
        token_total = 0

        for page in selected_pages:
            chunk = page["chunks"][0]
            token_total = self._append_if_budget_allows(packed, chunk, selected_counts, token_total)

        for page in selected_pages:
            page_id = str(page["page_id"])
            max_chunks = self._max_chunks_for_page(page_id, exact_page_keys)
            for chunk in page["chunks"][1:max_chunks]:
                if selected_counts.get(page_id, 0) >= max_chunks:
                    break
                token_total = self._append_if_budget_allows(packed, chunk, selected_counts, token_total)

        return packed

    def _append_if_budget_allows(
        self,
        packed: list[Source],
        source: Source,
        selected_counts: dict[str, int],
        token_total: int,
    ) -> int:
        token_count = self._token_count(source.text)
        if token_total + token_count > self._settings.retrieval_context_token_budget:
            return token_total
        packed.append(source)
        page_id = str(source.page_id)
        selected_counts[page_id] = selected_counts.get(page_id, 0) + 1
        return token_total + token_count

    def _token_count(self, text: str) -> int:
        return len(self._encoding.encode(text))

    def _sort_chunks(self, page_id: str, chunks: list[Source], exact_page_keys: set[str]) -> list[Source]:
        if page_id in exact_page_keys:
            return sorted(chunks, key=lambda source: source.chunk_index if source.chunk_index is not None else 0)
        return sorted(chunks, key=lambda source: source.score, reverse=True)

    def _max_chunks_for_page(self, page_id: str, exact_page_keys: set[str]) -> int:
        if page_id in exact_page_keys:
            return self._settings.retrieval_exact_page_max_chunks
        return self._settings.retrieval_max_chunks_per_page

    def _token_encoder(self) -> Any:
        try:
            return tiktoken.get_encoding("cl100k_base")
        except Exception:
            return tiktoken.encoding_for_model("gpt-4")
