"""Thin REST clients for Gemini and OpenAI structured (JSON-schema) output."""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from .schema import json_schema_gemini, json_schema_openai


class TransientLLMError(RuntimeError):
    """Rate limit, timeout or server error. Safe to retry."""


class PermanentLLMError(RuntimeError):
    """Bad key, bad request, blocked content. Retrying will not help."""


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


def _raise_for(resp: httpx.Response, provider: str) -> None:
    if resp.status_code == 200:
        return
    msg = f"{provider} HTTP {resp.status_code}: {resp.text[:300]}"
    if resp.status_code in (408, 409, 429) or resp.status_code >= 500:
        raise TransientLLMError(msg)
    raise PermanentLLMError(msg)


class LLMClient:
    def __init__(self, provider: str, model: str, api_key: str, temperature: float = 0.0,
                 timeout: float = 60.0):
        if provider not in ("gemini", "openai"):
            raise ValueError(f"Unsupported LLM_PROVIDER {provider!r}; use 'gemini' or 'openai'")
        if not api_key:
            key_name = "GEMINI_API_KEY" if provider == "gemini" else "OPENAI_API_KEY"
            raise PermanentLLMError(f"{key_name} is not set")
        self.provider, self.model, self.api_key = provider, model, api_key
        self.temperature = temperature
        self._http = httpx.Client(timeout=timeout)

    def complete_json(self, system: str, user: str) -> LLMResponse:
        start = time.monotonic()
        try:
            if self.provider == "gemini":
                text, tin, tout = self._gemini(system, user)
            else:
                text, tin, tout = self._openai(system, user)
        except httpx.TransportError as exc:
            raise TransientLLMError(f"{self.provider} network error: {exc}") from exc
        return LLMResponse(text, tin, tout, int((time.monotonic() - start) * 1000))

    def _gemini(self, system: str, user: str) -> tuple[str, int, int]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": self.temperature,
                "responseMimeType": "application/json",
                "responseSchema": json_schema_gemini(),
                "maxOutputTokens": 512,
            },
        }
        resp = self._http.post(url, json=body, headers={"x-goog-api-key": self.api_key})
        _raise_for(resp, "gemini")
        data = resp.json()
        usage = data.get("usageMetadata") or {}
        tin = int(usage.get("promptTokenCount") or 0)
        # thinking tokens are billed as output
        tout = int(usage.get("candidatesTokenCount") or 0) + int(usage.get("thoughtsTokenCount") or 0)
        cands = data.get("candidates") or []
        if not cands:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
            raise PermanentLLMError(f"gemini returned no output ({reason})")
        parts = (cands[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts)
        return text, tin, tout

    def _openai(self, system: str, user: str) -> tuple[str, int, int]:
        body: dict = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "job_classification", "strict": True,
                                "schema": json_schema_openai()},
            },
            "max_completion_tokens": 512,
        }
        # Reasoning models reject a temperature parameter.
        if not self.model.startswith(("o1", "o3", "o4", "gpt-5", "gpt-6")):
            body["temperature"] = self.temperature
        resp = self._http.post(
            "https://api.openai.com/v1/chat/completions", json=body,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        _raise_for(resp, "openai")
        data = resp.json()
        usage = data.get("usage") or {}
        msg = (data.get("choices") or [{}])[0].get("message") or {}
        if msg.get("refusal"):
            raise PermanentLLMError(f"openai refused: {msg['refusal']}")
        return msg.get("content") or "", int(usage.get("prompt_tokens") or 0), \
            int(usage.get("completion_tokens") or 0)
