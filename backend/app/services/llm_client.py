"""
Answer-generator adapter for Ask AI (W13-02 / W13-03).

The chatbot only ever hands this module text that has already been retrieved
and role-scoped by chatbot_service. This module turns that text into prose and
nothing else: it never touches the database. That split is what lets the
"provided agent" in the ITP2 guide replace OpenRouter later without changing
retrieval or security.

Configuration (root .env, backend only):
    OPENROUTER_API_KEY   required; blank means the LLM is unavailable
    OPENROUTER_MODEL     optional; defaults to DEFAULT_MODEL
"""

from __future__ import annotations

import logging
import os

import httpx

from app.config import load_environment

load_environment()

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-2.5-flash-lite"
TIMEOUT_SECONDS = 30.0


class LLMUnavailableError(Exception):
    """The model could not produce an answer (no key, network, provider error)."""


def llm_model() -> str:
    return os.getenv("OPENROUTER_MODEL", "").strip() or DEFAULT_MODEL


def llm_configured() -> bool:
    return bool(os.getenv("OPENROUTER_API_KEY", "").strip())


def generate_answer(messages: list[dict[str, str]], temperature: float = 0.2) -> str:
    """Send chat messages to OpenRouter and return the reply text."""
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise LLMUnavailableError("OPENROUTER_API_KEY is not set.")

    try:
        response = httpx.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "X-OpenRouter-Title": "SIT Lab Budget Monitoring",
            },
            json={
                "model": llm_model(),
                "messages": messages,
                "temperature": temperature,
            },
            timeout=TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        logger.warning("OpenRouter request failed: %s", exc)
        raise LLMUnavailableError("Could not reach the AI provider.") from exc

    if response.status_code != 200:
        logger.warning(
            "OpenRouter returned %s: %s", response.status_code, response.text[:500]
        )
        raise LLMUnavailableError(
            f"AI provider returned HTTP {response.status_code}."
        )

    body = response.json()
    # OpenRouter can report provider failures inside a 200 response.
    if "error" in body:
        logger.warning("OpenRouter error payload: %s", body["error"])
        raise LLMUnavailableError("AI provider reported an error.")

    try:
        text = body["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMUnavailableError("AI provider returned an unexpected response.") from exc

    text = text.strip()
    if not text:
        raise LLMUnavailableError("AI provider returned an empty answer.")
    return text
