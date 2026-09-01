from typing import Literal


GenerationErrorCode = Literal[
    "inference_model_missing",
    "inference_model_unavailable",
    "inference_timeout",
    "inference_unavailable",
    "inference_empty_response",
    "generation_failed",
]


class GenerationError(RuntimeError):
    def __init__(self, code: GenerationErrorCode, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.__cause__ = cause
