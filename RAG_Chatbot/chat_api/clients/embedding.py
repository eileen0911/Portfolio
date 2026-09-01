import requests

from chat_api.config import Settings
from chat_api.retrieval.errors import RetrievalError


class EmbeddingClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._session = requests.Session()
        self._session.trust_env = settings.use_env_proxy

    def embed(self, text: str) -> list[float]:
        try:
            response = self._session.post(
                f"{self._settings.embedding_base_url.rstrip('/')}/embeddings",
                json={"input": text, "model": self._settings.embedding_model},
                headers={
                    "Authorization": f"Bearer {self._settings.embedding_api_key or 'EMPTY'}",
                    "Content-Type": "application/json",
                },
                timeout=self._settings.request_timeout_seconds,
            )
            response.raise_for_status()
            embedding = response.json()["data"][0]["embedding"]
            if isinstance(embedding, str):
                raise TypeError("Embedding API returned an encoded embedding string")
            return list(embedding)
        except requests.Timeout as exc:
            raise RetrievalError("embedding_timeout", "Embedding API timed out", exc) from exc
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
            raise RetrievalError("embedding_unavailable", "Embedding API request failed", exc) from exc
