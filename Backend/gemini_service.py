"""
gemini_service.py
==================
Two Gemini-powered features, both grounded strictly in real FarmScore
data — never inventing farm-specific numbers:

- generate_insight(context)   → short explanation of a /calculate result
- generate_chat_reply(...)    → chatbot replies (general + farm-specific)

If GEMINI_API_KEY is not set, or any call fails, these return None —
callers treat that as "unavailable this time", never as an error that
should block the rest of the response.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-3.1-flash-lite"
GEMINI_FALLBACK_MODEL = "gemini-3.5-flash"
REQUEST_TIMEOUT_S = 12


def _gemini_url(model: str) -> str:
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _call_gemini(model: str, api_key: str, contents: list, system_text: Optional[str] = None,
                  temperature: float = 0.3, max_tokens: int = 220) -> Optional[str]:
    """Single Gemini call. Raises requests exceptions on failure so the
    caller's retry/fallback loop can react to them."""
    payload: Dict[str, Any] = {
        "contents": contents,
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }
    if system_text:
        payload["systemInstruction"] = {"parts": [{"text": system_text}]}

    response = requests.post(
        _gemini_url(model),
        params={"key": api_key},
        json=payload,
        timeout=REQUEST_TIMEOUT_S,
    )
    response.raise_for_status()
    data = response.json()

    candidates = data.get("candidates") or []
    if not candidates:
        logger.warning("Gemini (%s) returned no candidates: %s", model, data)
        return None

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    return text or None


def _call_with_fallback(api_key: str, contents: list, **kwargs) -> Optional[str]:
    """Try the primary model, then the fallback model on a 404 (usually
    a deprecated/renamed model), never raising — returns None on failure."""
    for model in (GEMINI_MODEL, GEMINI_FALLBACK_MODEL):
        try:
            return _call_gemini(model, api_key, contents, **kwargs)
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            logger.warning("Gemini (%s) HTTP error %s: %s", model, status, exc)
            if status == 404 and model != GEMINI_FALLBACK_MODEL:
                continue
            return None
        except requests.exceptions.RequestException as exc:
            logger.warning("Gemini (%s) request failed: %s", model, exc)
            return None
        except (KeyError, IndexError, ValueError) as exc:
            logger.warning("Gemini (%s) response parsing failed: %s", model, exc)
            return None
    return None


# ===========================================================================
# 1. AI Insight — one-shot explanation of a /calculate result
# ===========================================================================

def _build_insight_prompt(context: Dict[str, Any]) -> str:
    components = context.get("components", {})
    lines = []
    for key, c in components.items():
        if not c:
            continue
        lines.append(
            f"- {key}: raw value {c.get('raw_value')} {c.get('unit') or ''}, "
            f"sub-score {c.get('sub_score')}/100, weight {c.get('weight')}%, "
            f"source {c.get('source')}"
        )
    components_text = "\n".join(lines) or "No component data available."

    crop = context.get("recommended_crops") or {}
    primary_crop = crop.get("primary", {}).get("crop") if crop.get("primary") else None
    climate = context.get("climate_risk") or {}

    return f"""You are helping a bank loan officer read a farmland suitability report.
Below are the ACTUAL computed values from satellite data. Do not invent,
estimate, or restate any number that is not given below. Do not mention
a specific yield, rupee amount, or percentage that isn't listed here.
Write 3-4 short sentences, plain language, no headers or bullet points.

FarmScore: {context.get('score')}/900 ({context.get('grade')})
Component breakdown:
{components_text}

Top recommended crop: {primary_crop or "not available"}
Climate risk level: {climate.get('level', 'not available')}
Climate risk notes: {', '.join(climate.get('flags', [])) or 'none flagged'}
Surface water index (NDWI): {context.get('ndwi')}

Explain what this means for the land's suitability and what the officer
should keep in mind, using ONLY the numbers above."""


def generate_insight(context: Dict[str, Any]) -> Optional[str]:
    """Return a short grounded explanation of a /calculate result, or
    None if Gemini is unavailable."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.info("GEMINI_API_KEY not set — skipping AI insight")
        return None

    prompt = _build_insight_prompt(context)
    contents = [{"role": "user", "parts": [{"text": prompt}]}]
    return _call_with_fallback(api_key, contents, max_tokens=220)


# ===========================================================================
# 2. Chatbot — general agriculture Q&A + questions about the current farm
# ===========================================================================

CHAT_SYSTEM_INSTRUCTIONS = """You are FarmScore Assistant, a helpful agriculture and land-suitability
advisor built into a satellite-based farmland assessment tool used by bank
loan officers in India.

You can answer two kinds of questions:
1. General agriculture/satellite questions (e.g. "what is NDVI?", "which
   crops need less water?", "what does groundwater depletion mean?") —
   answer these from general knowledge, plainly and briefly.
2. Questions about the specific farm currently being evaluated — answer
   these ONLY using the "Current farm data" block below, if provided.
   Never invent a score, crop name, distance, or any other number for
   this specific farm that isn't in that block. If the data needed to
   answer isn't in the block, say so plainly instead of guessing.

Keep answers short (2-5 sentences), plain language, no markdown headers."""


def _format_farm_context(farm_context: Optional[Dict[str, Any]]) -> str:
    if not farm_context:
        return "No farm has been calculated yet in this session."

    components = farm_context.get("components", {})
    comp_lines = "\n".join(
        f"- {k}: {v.get('raw_value')} {v.get('unit') or ''} "
        f"(sub-score {v.get('sub_score')}/100, weight {v.get('weight')}%, source {v.get('source')})"
        for k, v in components.items() if v
    )
    crop = (farm_context.get("recommended_crops") or {}).get("primary", {})
    climate = farm_context.get("climate_risk") or {}

    return f"""FarmScore: {farm_context.get('score')}/900 ({farm_context.get('grade')})
Components:
{comp_lines or "not available"}
Top recommended crop: {crop.get('crop', 'not available')} ({crop.get('score', '')}%)
Climate risk: {climate.get('level', 'not available')} — {', '.join(climate.get('flags', [])) or 'no flags'}
Surface water (NDWI): {farm_context.get('ndwi')}
Coordinates: {farm_context.get('coordinates')}"""


def generate_chat_reply(
    message: str,
    history: Optional[list] = None,
    farm_context: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Return a grounded chat reply, or None if Gemini is unavailable."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.info("GEMINI_API_KEY not set — skipping chat reply")
        return None

    contents = []
    for turn in (history or [])[-10:]:  # cap history to keep prompts small
        role = "model" if turn.get("role") == "assistant" else "user"
        text = turn.get("text", "")
        if text:
            contents.append({"role": role, "parts": [{"text": text}]})
    contents.append({"role": "user", "parts": [{"text": message}]})

    system_block = CHAT_SYSTEM_INSTRUCTIONS + "\n\nCurrent farm data:\n" + _format_farm_context(farm_context)
    return _call_with_fallback(api_key, contents, system_text=system_block, temperature=0.4, max_tokens=300)
