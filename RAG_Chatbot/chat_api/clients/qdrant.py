import requests

from chat_api.config import Settings
from chat_api.models import Source
from chat_api.retrieval.errors import RetrievalError


class QdrantStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._session = requests.Session()
        self._session.trust_env = settings.use_env_proxy

    @property
    def collection_name(self) -> str:
        return self._settings.qdrant_collection

    def query_dense(self, vector: list[float]) -> list[Source]:
        try:
            response = self._session.post(
                f"{self._settings.qdrant_url.rstrip('/')}/collections/{self.collection_name}/points/query",
                json={
                    "query": vector,
                    "using": "dense",
                    "limit": self._settings.retrieval_candidate_k,
                    "with_payload": True,
                    "score_threshold": self._settings.retrieval_score_threshold,
                },
                timeout=self._settings.request_timeout_seconds,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            raise RetrievalError("qdrant_timeout", "Qdrant query timed out", exc) from exc
        except requests.RequestException as exc:
            raise RetrievalError("qdrant_unavailable", "Qdrant query failed", exc) from exc

        try:
            result = response.json().get("result", [])
        except ValueError as exc:
            raise RetrievalError("qdrant_bad_response", "Qdrant returned invalid JSON", exc) from exc
        points = result.get("points", []) if isinstance(result, dict) else result
        sources: list[Source] = []
        for point in points:
            sources.append(self._source_from_point(point, score=float(point.get("score", 0.0))))
        return sources

    def query_page_chunks(self, page_ids: list[int | str], limit_per_page: int = 20) -> list[Source]:
        sources: list[Source] = []
        for page_id in page_ids:
            try:
                response = self._session.post(
                    f"{self._settings.qdrant_url.rstrip('/')}/collections/{self.collection_name}/points/scroll",
                    json={
                        "filter": {"must": [{"key": "page_id", "match": {"value": page_id}}]},
                        "limit": limit_per_page,
                        "with_payload": True,
                        "with_vectors": False,
                    },
                    timeout=self._settings.request_timeout_seconds,
                )
                response.raise_for_status()
            except requests.Timeout as exc:
                raise RetrievalError("qdrant_timeout", "Qdrant page chunk query timed out", exc) from exc
            except requests.RequestException as exc:
                raise RetrievalError("qdrant_unavailable", "Qdrant page chunk query failed", exc) from exc

            try:
                result = response.json().get("result", [])
            except ValueError as exc:
                raise RetrievalError("qdrant_bad_response", "Qdrant returned invalid JSON", exc) from exc
            points = result.get("points", result) if isinstance(result, dict) else result
            sources.extend(self._source_from_point(point, score=0.0) for point in points)
        return sorted(
            sources,
            key=lambda source: (str(source.page_id), source.chunk_index if source.chunk_index is not None else 0),
        )

    def _source_from_point(self, point: dict, score: float) -> Source:
        payload = point.get("payload") or {}
        return Source(
            page_id=payload.get("page_id"),
            title=payload.get("page_title", "Unknown"),
            chunk_index=payload.get("chunk_index"),
            score=score,
            text=payload.get("chunk_text", ""),
            source_category=payload.get("source_category"),
            book_name=payload.get("book_name"),
            tags=payload.get("tags", []),
        )
