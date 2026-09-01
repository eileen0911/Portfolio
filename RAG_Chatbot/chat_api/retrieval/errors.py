from typing import Literal


RetrievalErrorCode = Literal[
    "embedding_timeout",
    "embedding_unavailable",
    "embedding_empty_vector",
    "embedding_dimension_mismatch",
    "qdrant_timeout",
    "qdrant_unavailable",
    "qdrant_bad_response",
    "retrieval_failed",
]


class RetrievalError(RuntimeError):
    def __init__(self, code: RetrievalErrorCode, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.__cause__ = cause
