import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name, str(default))
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


def _env_float(name: str, default: float) -> float:
    raw = _env(name, str(default))
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env(name, "1" if default else "0").lower()
    return raw in {"1", "true", "yes", "on"}


def _default_session_db_path() -> str:
    return str(Path(__file__).resolve().parent.parent / "data" / "chat_sessions.sqlite3")


@dataclass(frozen=True)
class Settings:
    app_name: str
    environment: str

    qdrant_url: str
    qdrant_collection: str

    embedding_base_url: str
    embedding_model: str
    embedding_api_key: str
    dense_vector_size: int

    inference_base_url: str
    inference_model: str
    inference_api_key: str
    inference_timeout_seconds: float

    retrieval_candidate_k: int
    retrieval_top_k: int
    retrieval_max_chunks_per_page: int
    retrieval_exact_page_max_chunks: int
    retrieval_context_token_budget: int
    retrieval_score_threshold: float
    request_timeout_seconds: float
    use_env_proxy: bool
    conversation_timeout_seconds: float
    ai_session_db_path: str
    ai_session_idle_timeout_seconds: float
    ai_history_max_turns: int
    ai_history_max_chars: int
    chat_cta_enabled: bool = False
    chat_cta_official_site_nav_enabled: bool = False

    def __post_init__(self) -> None:
        if self.retrieval_candidate_k < self.retrieval_top_k:
            raise ValueError("RETRIEVAL_CANDIDATE_K must be greater than or equal to RETRIEVAL_CONTEXT_TOP_K")
        if self.retrieval_top_k < 1:
            raise ValueError("RETRIEVAL_CONTEXT_TOP_K must be a positive integer")
        if self.retrieval_max_chunks_per_page < 1:
            raise ValueError("RETRIEVAL_MAX_CHUNKS_PER_PAGE must be a positive integer")
        if self.retrieval_exact_page_max_chunks < 1:
            raise ValueError("RETRIEVAL_EXACT_PAGE_MAX_CHUNKS must be a positive integer")
        if self.retrieval_context_token_budget < 1:
            raise ValueError("RETRIEVAL_CONTEXT_TOKEN_BUDGET must be a positive integer")
        if not self.ai_session_db_path:
            raise ValueError("AI_SESSION_DB_PATH must not be empty")
        if self.ai_session_idle_timeout_seconds <= 0:
            raise ValueError("AI_SESSION_IDLE_TIMEOUT_SECONDS must be greater than 0")
        if self.ai_history_max_turns < 0:
            raise ValueError("AI_HISTORY_MAX_TURNS must be greater than or equal to 0")
        if self.ai_history_max_chars < 1:
            raise ValueError("AI_HISTORY_MAX_CHARS must be a positive integer")


def get_settings() -> Settings:
    return Settings(
        app_name=_env("CHAT_API_APP_NAME", "RAG Chat API"),
        environment=_env("CHAT_API_ENV", "demo"),
        qdrant_url=_env("QDRANT_URL", "http://localhost:6333"),
        qdrant_collection=_env("QDRANT_COLLECTION", "demo_knowledge_base"),
        embedding_base_url=_env("EMBEDDING_BASE_URL", "http://localhost:8001/v1"),
        embedding_model=_env("EMBEDDING_MODEL", "demo-embedding-model"),
        embedding_api_key=_env("EMBEDDING_API_KEY", ""),
        dense_vector_size=_env_int("DENSE_VECTOR_SIZE", 4096),
        inference_base_url=_env("INFERENCE_BASE_URL", "http://localhost:8002/v1"),
        inference_model=_env("INFERENCE_MODEL", "demo-chat-model"),
        inference_api_key=_env("INFERENCE_API_KEY", ""),
        inference_timeout_seconds=_env_float("INFERENCE_TIMEOUT_SECONDS", 180.0),
        retrieval_candidate_k=_env_int("RETRIEVAL_CANDIDATE_K", 12),
        retrieval_top_k=_env_int("RETRIEVAL_CONTEXT_TOP_K", _env_int("RETRIEVAL_TOP_K", 5)),
        retrieval_max_chunks_per_page=_env_int("RETRIEVAL_MAX_CHUNKS_PER_PAGE", 2),
        retrieval_exact_page_max_chunks=_env_int("RETRIEVAL_EXACT_PAGE_MAX_CHUNKS", 6),
        retrieval_context_token_budget=_env_int("RETRIEVAL_CONTEXT_TOKEN_BUDGET", 2200),
        retrieval_score_threshold=_env_float("RETRIEVAL_SCORE_THRESHOLD", 0.4),
        request_timeout_seconds=_env_float("REQUEST_TIMEOUT_SECONDS", 30.0),
        use_env_proxy=_env_bool("USE_ENV_PROXY", False),
        conversation_timeout_seconds=_env_float("CONVERSATION_TIMEOUT_SECONDS", 1800.0),
        ai_session_db_path=_env("AI_SESSION_DB_PATH", _default_session_db_path()),
        ai_session_idle_timeout_seconds=_env_float("AI_SESSION_IDLE_TIMEOUT_SECONDS", 1800.0),
        ai_history_max_turns=_env_int("AI_HISTORY_MAX_TURNS", 10),
        ai_history_max_chars=_env_int("AI_HISTORY_MAX_CHARS", 12000),
        chat_cta_enabled=_env_bool("CHAT_CTA_ENABLED", False),
        chat_cta_official_site_nav_enabled=_env_bool("CHAT_CTA_OFFICIAL_SITE_NAV_ENABLED", False),
    )

