"""
Answer-generator adapter for Ask AI (W13-02 / W13-03).

The chatbot only ever hands this module text that has already been retrieved
and role-scoped by chatbot_service. This module turns that text into prose and
nothing else: it never touches the database. That split is what lets the
"provided agent" in the ITP2 guide replace OpenRouter later without changing
retrieval or security.

Configuration (root .env, backend only). Any OpenAI-compatible chat
completions API works; switching provider is an .env change, not a code one:

    LLM_API_KEY    required; blank means the LLM is unavailable
    LLM_BASE_URL   optional; defaults to OpenRouter (DEFAULT_BASE_URL)
    LLM_MODEL      optional; defaults to DEFAULT_MODEL. Use the provider's own
                   model names ("google/gemini-2.5-flash-lite" on OpenRouter,
                   "gpt-4o-mini" on OpenAI).

    OpenRouter:  LLM_BASE_URL=https://openrouter.ai/api/v1
    OpenAI:      LLM_BASE_URL=https://api.openai.com/v1

The older OPENROUTER_API_KEY / OPENROUTER_MODEL names are still read when the
LLM_* ones are not set, so existing .env files keep working.

TODO(client-handover): OpenRouter is only the interim provider while the
client sets up OpenAI. Every OpenRouter mention in this file (tagged
TODO(client-handover)) will be removed before final submission to the client.
"""

from __future__ import annotations

import logging
import os

import httpx

from app.config import load_environment

load_environment()

logger = logging.getLogger(__name__)

# TODO(client-handover): OpenRouter defaults — will be removed before final
# submission to the client (switch to https://api.openai.com/v1 + gpt-4o-mini).
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "google/gemini-2.5-flash-lite"
TIMEOUT_SECONDS = 30.0


class LLMUnavailableError(Exception):
    """The model could not produce an answer (no key, network, provider error)."""


# TODO(client-handover): the OPENROUTER_* fallback names read through _env()
# will be removed before final submission to the client (read LLM_* only).
def _env(name: str, legacy: str) -> str:
    return os.getenv(name, "").strip() or os.getenv(legacy, "").strip()


def llm_model() -> str:
    return _env("LLM_MODEL", "OPENROUTER_MODEL") or DEFAULT_MODEL


def llm_base_url() -> str:
    return (os.getenv("LLM_BASE_URL", "").strip() or DEFAULT_BASE_URL).rstrip("/")


def llm_configured() -> bool:
    return bool(_env("LLM_API_KEY", "OPENROUTER_API_KEY"))


def generate_answer(messages: list[dict[str, str]], temperature: float = 0.2) -> str:
    """Send chat messages to the configured provider and return the reply text."""
    api_key = _env("LLM_API_KEY", "OPENROUTER_API_KEY")
    if not api_key:
        raise LLMUnavailableError("LLM_API_KEY is not set.")

    base_url = llm_base_url()
    headers = {"Authorization": f"Bearer {api_key}"}
    # TODO(client-handover): OpenRouter-only header — will be removed before
    # final submission to the client.
    if "openrouter.ai" in base_url:
        # OpenRouter-only app attribution header; other providers don't need it.
        headers["X-OpenRouter-Title"] = "SIT Lab Budget Monitoring"
    payload = {
        "model": llm_model(),
        "messages": messages,
        "temperature": temperature,
    }

    response = _post(f"{base_url}/chat/completions", headers, payload)
    if response.status_code == 400 and "temperature" in response.text:
        # Some models (e.g. OpenAI's reasoning models) only accept the default
        # temperature. Retry once without it rather than failing the answer.
        payload.pop("temperature")
        response = _post(f"{base_url}/chat/completions", headers, payload)

    if response.status_code != 200:
        logger.warning(
            "LLM provider returned %s: %s", response.status_code, response.text[:500]
        )
        raise LLMUnavailableError(f"AI provider returned HTTP {response.status_code}.")

    body = response.json()
    # OpenRouter can report provider failures inside a 200 response.
    # TODO(client-handover): OpenRouter wording — will be removed before final
    # submission to the client. Keep the check itself; it is harmless on OpenAI.
    if "error" in body:
        logger.warning("LLM provider error payload: %s", body["error"])
        raise LLMUnavailableError("AI provider reported an error.")

    try:
        text = body["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMUnavailableError(
            "AI provider returned an unexpected response."
        ) from exc

    text = text.strip()
    if not text:
        raise LLMUnavailableError("AI provider returned an empty answer.")
    return text


def _post(url: str, headers: dict[str, str], payload: dict) -> httpx.Response:
    try:
        return httpx.post(url, headers=headers, json=payload, timeout=TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        logger.warning("LLM request failed: %s", exc)
        raise LLMUnavailableError("Could not reach the AI provider.") from exc
