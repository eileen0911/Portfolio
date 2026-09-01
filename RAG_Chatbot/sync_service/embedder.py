import os
import time
from typing import List, Callable, Any
from functools import wraps

import requests


def _retry_with_backoff(retries: int = 3, backoff_in_seconds: float = 1.0) -> Callable:
    """
    Decorator to implement network error retry mechanism with exponential backoff.
    
    Args:
        retries: Maximum number of retries before giving up.
        backoff_in_seconds: Base sleep duration in seconds for exponential backoff.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            attempt = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempt += 1
                    if attempt > retries:
                        raise e
                    sleep_time = backoff_in_seconds * (2 ** (attempt - 1))
                    time.sleep(sleep_time)
        return wrapper
    return decorator


def _embedding_url() -> str:
    api_url = os.getenv("EMBEDDING_BASE_URL", "http://localhost:8880/v1")
    return f"{api_url.rstrip('/')}/embeddings"


def _headers() -> dict[str, str]:
    api_key = os.getenv("EMBEDDING_API_KEY", "EMPTY")
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


@_retry_with_backoff(retries=3)
def embed_text(text: str) -> List[float]:
    """
    Embed a single text using the configured OpenAI-compatible embedding API.
    
    Args:
        text (str): The text to embed.
        
    Returns:
        List[float]: A list of float values representing the dense embedding vector.
    """
    model = os.getenv("EMBEDDING_MODEL", "Qwen3-Embedding-8B-GGUF")

    response = requests.post(
        _embedding_url(),
        json={"input": text, "model": model},
        headers=_headers(),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]


@_retry_with_backoff(retries=3)
def embed_batch(texts: List[str]) -> List[List[float]]:
    """
    Embed multiple texts in a single batch using the configured OpenAI-compatible embedding API.
    
    Args:
        texts (List[str]): A list of texts to embed.
        
    Returns:
        List[List[float]]: A list where each element is the embedding vector for the corresponding input list order.
    """
    if not texts:
        return []
        
    model = os.getenv("EMBEDDING_MODEL", "Qwen3-Embedding-8B-GGUF")
    response = requests.post(
        _embedding_url(),
        json={"input": texts, "model": model},
        headers=_headers(),
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()["data"]
    sorted_data = sorted(data, key=lambda item: item.get("index", 0))
    return [item["embedding"] for item in sorted_data]
