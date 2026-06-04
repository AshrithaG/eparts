"""LLM backend abstraction.

The rest of the pipeline only sees the abstract `LLMClient`. Concrete
backends:

  * `OllamaClient`   — local model via the Ollama HTTP API.
  * `MockLLMClient`  — canned responses for unit tests / `--mock` demo.
  * `AzureOpenAIClient` — stub for the Azure path once the team
                          enables egress. Raises `NotImplementedError`.

The Ollama client passes the Pydantic JSON schema directly to Ollama's
`format=` parameter (supported in Ollama 0.5+), which constrains
decoding so the model literally cannot emit a non-conforming object.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any


class LLMClient(ABC):
    """Backend-agnostic interface.

    `extract()` returns the raw response string (which `extract.py`
    parses into `LLMPrediction`) and a metadata dict with whatever
    timing / token info the backend exposes.
    """

    @property
    @abstractmethod
    def model_id(self) -> str:
        """A stable identifier for provenance, e.g. `ollama/qwen2.5:7b-instruct`."""

    @abstractmethod
    def extract(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        options: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Run one extraction call. Returns (raw_response_text, metadata)."""


# ---------------------------------------------------------------------------
# Ollama (local)
# ---------------------------------------------------------------------------

class OllamaClient(LLMClient):
    """Calls a model served by a local Ollama instance.

    The `format=schema` arg activates Ollama's JSON-schema constrained
    decoding, so the model is *forced* to produce a syntactically valid
    `LLMPrediction`. Semantic validity (values within the closed
    vocabulary) is enforced afterward by `extract.py`.
    """

    def __init__(
        self,
        model: str,
        host: str = "http://localhost:11434",
        default_options: dict[str, Any] | None = None,
    ) -> None:
        try:
            import ollama  # local import so unit tests don't require the dep
        except ImportError as e:  # pragma: no cover - exercised in real runs
            raise RuntimeError(
                "The `ollama` Python package is not installed. "
                "Run `pip install -r requirements.txt`."
            ) from e
        self._ollama = ollama
        self._client = ollama.Client(host=host)
        self._model = model
        self._host = host
        self._default_options = dict(default_options or {})

    @property
    def model_id(self) -> str:
        return f"ollama/{self._model}"

    def extract(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        options: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        opts = {**self._default_options, **(options or {})}
        response = self._client.chat(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            format=schema,
            options=opts,
        )
        # ollama-python returns a dict-like; index defensively in case
        # the package version changes the shape.
        msg = response.get("message", {}) if isinstance(response, dict) else response.message
        raw = msg["content"] if isinstance(msg, dict) else msg.content
        meta = {
            "host": self._host,
            "options": opts,
            "eval_count": _safe_get(response, "eval_count"),
            "eval_duration_ns": _safe_get(response, "eval_duration"),
            "total_duration_ns": _safe_get(response, "total_duration"),
        }
        return raw, meta


def _safe_get(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


# ---------------------------------------------------------------------------
# Mock (tests + --mock demo)
# ---------------------------------------------------------------------------

class MockLLMClient(LLMClient):
    """Returns a canned response.

    Two ways to use it:

    1. Pass a dict ``{substring_to_match_in_user_prompt: response_json}``.
       The first key whose substring appears in the user prompt wins.
    2. Pass a callable ``(system_prompt, user_prompt) -> raw_response``.
    """

    def __init__(
        self,
        canned: dict[str, str] | None = None,
        responder: Any = None,
        model: str = "mock",
    ) -> None:
        if canned is None and responder is None:
            raise ValueError("MockLLMClient needs either `canned` or `responder`.")
        self._canned = canned
        self._responder = responder
        self._model = model

    @property
    def model_id(self) -> str:
        return f"mock/{self._model}"

    def extract(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        options: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        if self._responder is not None:
            return self._responder(system_prompt, user_prompt), {"mock": True}
        # Match against the customer-query section only (delimited by
        # <<< ... >>> by prompt.py). Matching against the whole prompt
        # is wrong because catalog neighbors in the grounding pack
        # contain product strings that can collide with intended keys.
        assert self._canned is not None
        haystack = _extract_customer_query(user_prompt) or user_prompt
        for needle, response in self._canned.items():
            if needle and needle in haystack:
                return response, {"mock": True, "match": needle}
        # fall back to the first entry
        first_key = next(iter(self._canned))
        return self._canned[first_key], {"mock": True, "match": "default"}


def _extract_customer_query(prompt: str) -> str | None:
    """Pull out the text between the prompt's <<< ... >>> delimiters."""
    start = prompt.find("<<<")
    end = prompt.find(">>>", start + 3) if start != -1 else -1
    if start == -1 or end == -1:
        return None
    return prompt[start + 3 : end]


# ---------------------------------------------------------------------------
# Azure OpenAI (stub — wired in for §3.1 of the plan)
# ---------------------------------------------------------------------------

class AzureOpenAIClient(LLMClient):
    """Stub. Filled in once data-egress review unlocks the Azure path."""

    def __init__(self, deployment: str, **_: Any) -> None:
        self._deployment = deployment

    @property
    def model_id(self) -> str:
        return f"azure_openai/{self._deployment}"

    def extract(self, *_: Any, **__: Any) -> tuple[str, dict[str, Any]]:
        raise NotImplementedError(
            "AzureOpenAIClient is a stub. Fill in once the team has Azure OpenAI "
            "credentials and the data-egress review has been signed off — see "
            "LLM_Based_ML_Implementation_Plan.docx §3.1."
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_client(config: dict[str, Any]) -> LLMClient:
    """Construct a client from `config/model.yaml`'s parsed contents."""
    backend = config.get("backend", "ollama").lower()
    if backend == "ollama":
        return OllamaClient(
            model=config["model"],
            host=config.get("host", "http://localhost:11434"),
            default_options=config.get("options", {}),
        )
    if backend == "mock":
        # The mock mode for the demo script reads canned responses from
        # data/fixtures/mock_responses.json if present; otherwise it
        # echoes back an "insufficient_evidence" answer to every query.
        path = config.get("mock_responses_path")
        canned: dict[str, str]
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                canned = json.load(f)
        else:
            canned = {"": json.dumps({
                "product_type": "unknown",
                "product_type_alternatives": [],
                "attributes": [],
            })}
        return MockLLMClient(canned=canned, model=config.get("model", "mock"))
    if backend == "azure_openai":
        return AzureOpenAIClient(deployment=config["model"])
    raise ValueError(f"Unknown backend: {backend!r}")
