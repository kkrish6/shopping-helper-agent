"""Optional LLM layer. Works with any OpenAI-compatible endpoint.

Free options: Groq (https://console.groq.com) or Google Gemini's OpenAI-compatible
endpoint. Set LLM_API_KEY (and optionally LLM_BASE_URL / LLM_MODEL). Without a
key every function falls back to simple rules, so the agent still works.
"""
from __future__ import annotations

import json
import os
import re

import requests

BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
MODEL = os.getenv("LLM_MODEL", "llama-3.1-8b-instant")


def enabled() -> bool:
    return bool(os.getenv("LLM_API_KEY"))


def _chat(system: str, user: str) -> str:
    resp = requests.post(
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['LLM_API_KEY']}"},
        json={"model": MODEL, "temperature": 0.2,
              "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def parse_request(text: str) -> dict:
    """Turn 'earbuds under 1500 rupees' into {'query': 'earbuds', 'max_price': 1500}."""
    fallback = _parse_rules(text)
    if not enabled():
        return fallback
    try:
        out = _chat("Extract a shopping search. Reply with JSON only: "
                    '{"query": str, "max_price": number|null}.', text)
        data = json.loads(re.search(r"\{.*\}", out, re.S).group())
        return {"query": data.get("query") or fallback["query"], "max_price": data.get("max_price")}
    except Exception:
        return fallback


def _parse_rules(text: str) -> dict:
    m = re.search(r"(?:under|below|less than|upto|up to|<)\s*(?:rs\.?|₹|inr)?\s*([\d,]+)", text, re.I)
    max_price = float(m.group(1).replace(",", "")) if m else None
    query = re.sub(r"(?:under|below|less than|upto|up to|<).*$", "", text, flags=re.I).strip()
    return {"query": query or text, "max_price": max_price}


def explain(question: str, facts: dict) -> str | None:
    """Short buying advice grounded ONLY in the supplied facts."""
    if not enabled():
        return None
    try:
        return _chat("You are a careful Indian shopping assistant. Use only the JSON facts given; "
                     "do not invent prices or offers. Answer in 3 short lines.",
                     f"Question: {question}\nFacts: {json.dumps(facts, ensure_ascii=False)}")
    except Exception:
        return None
