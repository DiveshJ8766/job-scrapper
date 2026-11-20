"""LLM list prices in USD per 1M tokens, Standard (paid) tier, text input.

Pricing checked on 2026-11-20:
  Gemini: https://aistudio.google.com/docs/pricing (Standard paid tier)
  OpenAI: https://developers.openai.com/api/docs/pricing  -- the gpt-4o-mini row could not
          be confirmed on the official page that day; verify before relying on it, or set
          LLM_PRICE_INPUT_PER_M / LLM_PRICE_OUTPUT_PER_M in .env.

Note: on Gemini's free tier the actual bill is $0; costs reported here are what the same
usage would cost on the paid tier, which is the meaningful number for scaling.
"""

from __future__ import annotations

import os

PRICING_DATE = "2026-11-20"

PRICES_PER_M: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-2.5-flash": (0.30, 2.50),
    "gpt-4o-mini": (0.15, 0.60),  # unverified on official page on PRICING_DATE, see above
}


def price_for(model: str) -> tuple[float, float] | None:
    inp = os.getenv("LLM_PRICE_INPUT_PER_M", "").strip()
    out = os.getenv("LLM_PRICE_OUTPUT_PER_M", "").strip()
    if inp and out:
        return float(inp), float(out)
    return PRICES_PER_M.get(model)


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    p = price_for(model)
    if p is None:
        return 0.0
    return (input_tokens * p[0] + output_tokens * p[1]) / 1_000_000
