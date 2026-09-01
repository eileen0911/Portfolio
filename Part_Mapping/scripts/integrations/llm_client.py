from __future__ import annotations

import httpx
from openai import OpenAI


def make_llm_client(base_url: str, api_key: str, timeout: float = 60.0) -> OpenAI:
    """Create an OpenAI-compatible client for local or LAN LLM servers.

    trust_env=False prevents httpx from routing private LAN endpoints through
    HTTP(S)_PROXY environment variables, which commonly breaks llama.cpp servers.
    """
    http_client = httpx.Client(trust_env=False, timeout=timeout)
    return OpenAI(base_url=base_url, api_key=api_key, http_client=http_client)
