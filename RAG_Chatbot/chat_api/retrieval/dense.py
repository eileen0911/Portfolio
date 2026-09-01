from chat_api.clients.embedding import EmbeddingClient
from chat_api.clients.qdrant import QdrantStore
from chat_api.config import Settings
from chat_api.models import ChatIntake, Source
from chat_api.retrieval.base import Retriever
from chat_api.retrieval.context_packer import SourcePacker
from chat_api.retrieval.errors import RetrievalError
from chat_api.retrieval.product_matcher import exact_product_page_ids


class DenseRetriever(Retriever):
    def __init__(
        self,
        embedding_client: EmbeddingClient,
        qdrant_store: QdrantStore,
        settings: Settings,
    ) -> None:
        self._embedding_client = embedding_client
        self._qdrant_store = qdrant_store
        self._settings = settings
        self._source_packer = SourcePacker(settings)

    def retrieve(self, question: str, intake: ChatIntake | None = None) -> list[Source]:
        vector = self._embedding_client.embed(question)
        if not vector:
            raise RetrievalError("embedding_empty_vector", "Embedding API returned an empty vector")
        if len(vector) != self._settings.dense_vector_size:
            raise RetrievalError(
                "embedding_dimension_mismatch",
                f"Embedding vector dimension {len(vector)} does not match expected {self._settings.dense_vector_size}",
            )
        candidate_sources = self._qdrant_store.query_dense(vector)
        exact_page_ids = exact_product_page_ids(question, candidate_sources, intake.intent if intake else None)
        if exact_page_ids:
            candidate_sources = self._expand_page_chunks(candidate_sources, exact_page_ids)
        return self._source_packer.pack(question, candidate_sources, intake, exact_page_ids=exact_page_ids)

    def _expand_page_chunks(
        self,
        candidate_sources: list[Source],
        page_ids: list[int | str],
    ) -> list[Source]:
        page_scores = self._page_scores(candidate_sources)
        expanded = [
            source.model_copy(update={"score": page_scores.get(str(source.page_id), source.score)})
            for source in self._qdrant_store.query_page_chunks(page_ids)
        ]
        return self._merge_sources(expanded, candidate_sources)

    def _page_scores(self, sources: list[Source]) -> dict[str, float]:
        scores: dict[str, float] = {}
        for source in sources:
            key = str(source.page_id)
            scores[key] = max(scores.get(key, 0.0), source.score)
        return scores

    def _merge_sources(self, preferred: list[Source], fallback: list[Source]) -> list[Source]:
        merged: list[Source] = []
        seen: set[tuple[str, int | None, str]] = set()
        for source in [*preferred, *fallback]:
            key = (str(source.page_id), source.chunk_index, source.title)
            if key in seen:
                continue
            seen.add(key)
            merged.append(source)
        return merged
