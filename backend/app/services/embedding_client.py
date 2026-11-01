"""
Embedding adapter for RAG retrieval (W13-03A).

Turns text into vectors for knowledge_chunks and for search queries. Like
llm_client, it never touches the database and knows nothing about roles:
callers decide what gets embedded and filter by scope themselves.

Configuration (root .env, backend only). Switching provider is an .env
change, not a code one:

    EMBEDDING_PROVIDER   "local" or "api". Blank means embeddings are off and
                         Ask AI answers from the SQL fact sheet alone.
    EMBEDDING_MODEL      optional; defaults per provider (DEFAULT_MODELS).
    EMBEDDING_API_KEY    "api" only; required.
    EMBEDDING_BASE_URL   "api" only; any OpenAI-compatible /embeddings API,
                         defaults to OpenAI.
    EMBEDDING_MAX_DISTANCE  optional; cosine distance above which a search hit
                         counts as unrelated. Defaults per model
                         (DEFAULT_MAX_DISTANCES); with no default and no value
                         there is no cutoff. Measure it for a new model or new
                         data with: python -m app.scripts.probe_knowledge

    local:  runs in-process via fastembed (free, no key). The model downloads
            once from Hugging Face on first use. Install: pip install fastembed
    api:    OpenAI      EMBEDDING_BASE_URL=https://api.openai.com/v1
            Ollama      EMBEDDING_BASE_URL=http://localhost:11434/v1

Vectors from different models can't be compared, so every stored chunk records
embedding_model_id() and searches must filter on it. Changing provider or model
means re-indexing.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

import httpx

from app.config import load_environment

load_environment()

logger = logging.getLogger(__name__)

PROVIDERS = ("local", "api")
DEFAULT_MODELS = {
    "local": "BAAI/bge-small-en-v1.5",
    "api": "text-embedding-3-small",
}
DEFAULT_BASE_URL = "https://api.openai.com/v1"
# Each model spreads distances differently, so cutoffs are per model.
# bge-small: measured on the maxedout20cat + SIT_PR_20GROUPS_v5 test data
# (2026-10-20). Relevant questions' best hits were 0.21-0.36; unrelated ones
# ("hello", "which lab spent the most?", "bitcoin price") were 0.36-0.49.
# Re-measure on real client data before relying on it.
DEFAULT_MAX_DISTANCES = {
    "BAAI/bge-small-en-v1.5": 0.35,
}
TIMEOUT_SECONDS = 30.0
API_BATCH_SIZE = 100

_local_model: Any = None
_local_model_name: str | None = None
_local_lock = threading.Lock()


class EmbeddingUnavailableError(Exception):
    """Text could not be embedded (not configured, missing package, provider error)."""


def embedding_provider() -> str:
    return os.getenv("EMBEDDING_PROVIDER", "").strip().lower()


def embedding_model() -> str:
    provider = embedding_provider()
    return os.getenv("EMBEDDING_MODEL", "").strip() or DEFAULT_MODELS.get(provider, "")


def embedding_model_id() -> str:
    """Provider + model, stored on every chunk, e.g. "local:BAAI/bge-small-en-v1.5"."""
    return f"{embedding_provider()}:{embedding_model()}"


def embedding_base_url() -> str:
    return (os.getenv("EMBEDDING_BASE_URL", "").strip() or DEFAULT_BASE_URL).rstrip("/")


def embedding_max_distance() -> float | None:
    """Cutoff for relevant search hits; None means no cutoff."""
    raw = os.getenv("EMBEDDING_MAX_DISTANCE", "").strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            logger.warning("Ignoring EMBEDDING_MAX_DISTANCE=%r: not a number.", raw)
    return DEFAULT_MAX_DISTANCES.get(embedding_model())


def embedding_configured() -> bool:
    provider = embedding_provider()
    if provider == "local":
        return True
    if provider == "api":
        return bool(os.getenv("EMBEDDING_API_KEY", "").strip())
    return False


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed text to be stored and searched over (document chunks, PR-line cards)."""
    if not texts:
        return []
    provider = _require_provider()
    if provider == "local":
        return _local_embed(texts, query=False)
    return _api_embed(texts)


def embed_query(text: str) -> list[float]:
    """Embed a user's question for searching.

    Some local models (e.g. BGE) expect queries to be phrased differently from
    stored passages; fastembed's query_embed handles that.
    """
    provider = _require_provider()
    if provider == "local":
        return _local_embed([text], query=True)[0]
    return _api_embed([text])[0]


def _require_provider() -> str:
    provider = embedding_provider()
    if provider not in PROVIDERS:
        raise EmbeddingUnavailableError(
            "EMBEDDING_PROVIDER is not set to 'local' or 'api'."
        )
    if not embedding_configured():
        raise EmbeddingUnavailableError("EMBEDDING_API_KEY is not set.")
    return provider


def _local_embed(texts: list[str], *, query: bool) -> list[list[float]]:
    model = _get_local_model()
    try:
        vectors = model.query_embed(texts) if query else model.passage_embed(texts)
        return [[float(x) for x in vector] for vector in vectors]
    except Exception as exc:
        logger.warning("Local embedding failed: %s", exc)
        raise EmbeddingUnavailableError("Local embedding model failed.") from exc


def _get_local_model() -> Any:
    """Load the fastembed model once per process (loading takes seconds)."""
    global _local_model, _local_model_name
    name = embedding_model()
    with _local_lock:
        if _local_model is not None and _local_model_name == name:
            return _local_model
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise EmbeddingUnavailableError(
                "EMBEDDING_PROVIDER=local needs the fastembed package "
                "(pip install fastembed)."
            ) from exc
        try:
            _local_model = TextEmbedding(model_name=name)
        except Exception as exc:
            logger.warning("Could not load local embedding model %s: %s", name, exc)
            raise EmbeddingUnavailableError(
                f"Could not load local embedding model {name}."
            ) from exc
        _local_model_name = name
        return _local_model


def _api_embed(texts: list[str]) -> list[list[float]]:
    api_key = os.getenv("EMBEDDING_API_KEY", "").strip()
    url = f"{embedding_base_url()}/embeddings"
    headers = {"Authorization": f"Bearer {api_key}"}
    vectors: list[list[float]] = []
    for start in range(0, len(texts), API_BATCH_SIZE):
        batch = texts[start : start + API_BATCH_SIZE]
        payload = {"model": embedding_model(), "input": batch}
        try:
            response = httpx.post(
                url, headers=headers, json=payload, timeout=TIMEOUT_SECONDS
            )
        except httpx.HTTPError as exc:
            logger.warning("Embedding request failed: %s", exc)
            raise EmbeddingUnavailableError(
                "Could not reach the embedding provider."
            ) from exc

        if response.status_code != 200:
            logger.warning(
                "Embedding provider returned %s: %s",
                response.status_code,
                response.text[:500],
            )
            raise EmbeddingUnavailableError(
                f"Embedding provider returned HTTP {response.status_code}."
            )

        try:
            data = sorted(response.json()["data"], key=lambda item: item["index"])
            batch_vectors = [[float(x) for x in item["embedding"]] for item in data]
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingUnavailableError(
                "Embedding provider returned an unexpected response."
            ) from exc
        if len(batch_vectors) != len(batch):
            raise EmbeddingUnavailableError(
                "Embedding provider returned the wrong number of vectors."
            )
        vectors.extend(batch_vectors)
    return vectors
