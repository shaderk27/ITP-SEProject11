"""Embedding adapter: provider selection, API calls and failures. No network, no model download."""

from __future__ import annotations

import sys
import types

import httpx
import pytest

from app.services import embedding_client
from app.services.embedding_client import EmbeddingUnavailableError

ENV_VARS = (
    "EMBEDDING_PROVIDER",
    "EMBEDDING_MODEL",
    "EMBEDDING_API_KEY",
    "EMBEDDING_BASE_URL",
    "EMBEDDING_MAX_DISTANCE",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(embedding_client, "_local_model", None)
    monkeypatch.setattr(embedding_client, "_local_model_name", None)


def _api_env(monkeypatch, **extra):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "api")
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")
    for name, value in extra.items():
        monkeypatch.setenv(name, value)


def _response(status: int, body) -> httpx.Response:
    return httpx.Response(status, json=body, request=httpx.Request("POST", "http://x"))


def test_blank_provider_is_unavailable():
    assert embedding_client.embedding_configured() is False
    with pytest.raises(EmbeddingUnavailableError):
        embedding_client.embed_query("oscilloscope")


def test_unknown_provider_is_unavailable(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "bogus")
    with pytest.raises(EmbeddingUnavailableError):
        embedding_client.embed_documents(["x"])


def test_api_without_key_is_unavailable(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "api")
    assert embedding_client.embedding_configured() is False
    with pytest.raises(EmbeddingUnavailableError, match="EMBEDDING_API_KEY"):
        embedding_client.embed_query("x")


def test_model_id_defaults_per_provider(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    assert embedding_client.embedding_model_id() == "local:BAAI/bge-small-en-v1.5"
    _api_env(monkeypatch)
    assert embedding_client.embedding_model_id() == "api:text-embedding-3-small"
    monkeypatch.setenv("EMBEDDING_MODEL", "nomic-embed-text")
    assert embedding_client.embedding_model_id() == "api:nomic-embed-text"


def test_empty_document_list_skips_provider():
    assert embedding_client.embed_documents([]) == []


def test_api_posts_to_configured_url_and_keeps_input_order(monkeypatch):
    _api_env(monkeypatch, EMBEDDING_BASE_URL="http://localhost:11434/v1/")
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append((url, headers, json))
        # Provider returns items out of order; the client must sort by index.
        return _response(
            200,
            {
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ]
            },
        )

    monkeypatch.setattr(embedding_client.httpx, "post", fake_post)

    vectors = embedding_client.embed_documents(["first", "second"])

    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
    url, headers, payload = calls[0]
    assert url == "http://localhost:11434/v1/embeddings"
    assert headers["Authorization"] == "Bearer test-key"
    assert payload == {"model": "text-embedding-3-small", "input": ["first", "second"]}


def test_api_batches_large_inputs(monkeypatch):
    _api_env(monkeypatch)
    monkeypatch.setattr(embedding_client, "API_BATCH_SIZE", 2)
    batch_sizes = []

    def fake_post(url, headers, json, timeout):
        batch_sizes.append(len(json["input"]))
        return _response(
            200,
            {
                "data": [
                    {"index": i, "embedding": [float(i)]}
                    for i in range(len(json["input"]))
                ]
            },
        )

    monkeypatch.setattr(embedding_client.httpx, "post", fake_post)

    vectors = embedding_client.embed_documents(["a", "b", "c", "d", "e"])

    assert batch_sizes == [2, 2, 1]
    assert len(vectors) == 5


@pytest.mark.parametrize(
    "response",
    [
        _response(500, {"error": "boom"}),
        _response(200, {"unexpected": True}),
        _response(
            200, {"data": [{"index": 0, "embedding": [1.0]}]}
        ),  # 1 vector for 2 inputs
    ],
)
def test_api_bad_responses_are_unavailable(monkeypatch, response):
    _api_env(monkeypatch)
    monkeypatch.setattr(embedding_client.httpx, "post", lambda *a, **k: response)
    with pytest.raises(EmbeddingUnavailableError):
        embedding_client.embed_documents(["a", "b"])


def test_api_network_error_is_unavailable(monkeypatch):
    _api_env(monkeypatch)

    def fail(*args, **kwargs):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(embedding_client.httpx, "post", fail)
    with pytest.raises(EmbeddingUnavailableError, match="Could not reach"):
        embedding_client.embed_query("x")


class _FakeTextEmbedding:
    loads = 0

    def __init__(self, model_name):
        type(self).loads += 1
        self.model_name = model_name

    def passage_embed(self, texts):
        return ([1.0, float(len(t))] for t in texts)

    def query_embed(self, texts):
        return ([9.0, float(len(t))] for t in texts)


def _fake_fastembed(monkeypatch):
    _FakeTextEmbedding.loads = 0
    module = types.ModuleType("fastembed")
    module.TextEmbedding = _FakeTextEmbedding  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fastembed", module)


def test_local_uses_passage_and_query_modes_and_loads_once(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    _fake_fastembed(monkeypatch)

    assert embedding_client.embed_documents(["abc", "de"]) == [[1.0, 3.0], [1.0, 2.0]]
    assert embedding_client.embed_query("abcd") == [9.0, 4.0]
    assert _FakeTextEmbedding.loads == 1


def test_local_without_fastembed_is_unavailable(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setitem(sys.modules, "fastembed", None)  # makes the import fail
    with pytest.raises(EmbeddingUnavailableError, match="fastembed"):
        embedding_client.embed_query("x")


def test_max_distance_defaults_per_model_and_env_overrides(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    assert embedding_client.embedding_max_distance() == 0.35

    monkeypatch.setenv("EMBEDDING_MAX_DISTANCE", "0.42")
    assert embedding_client.embedding_max_distance() == 0.42

    monkeypatch.setenv("EMBEDDING_MAX_DISTANCE", "not-a-number")
    assert embedding_client.embedding_max_distance() == 0.35


def test_max_distance_unknown_model_has_no_cutoff(monkeypatch):
    _api_env(monkeypatch)
    assert embedding_client.embedding_max_distance() is None
