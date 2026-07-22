"""
gemini_service.py
==================
Generates a natural-language explanation of a FarmScore result using the
Gemini API — grounded strictly in the real numbers FarmScore already
computed (satellite data, score, components, crop recommendation, climate
risk). The model is instructed to explain and interpret those numbers,
never to invent new ones.

If GEMINI_API_KEY is not set, or the API call fails for any reason, this
returns None — the caller (app.py) treats that as "no AI insight this
time" and the rest of the response is unaffected. AI insight is always
an addition on top of the real data, never a replacement for it.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)
REQUEST_TIMEOUT_S = 12


def _build_prompt(context: Dict[str, Any]) -> str:
    """Build a prompt that hands Gemini only real, already-computed
    numbers and instructs it to interpret them, not invent new ones.
    """
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

    prompt = f"""You are helping a bank loan officer read a farmland suitability report.
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

    return prompt


def generate_insight(context: Dict[str, Any]) -> Optional[str]:
    """Return a short grounded explanation string, or None if unavailable."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.info("GEMINI_API_KEY not set — skipping AI insight")
        return None

    prompt = _build_prompt(context)

   try:
    response = requests.post(
        GEMINI_URL,
        params={"key": api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 220,
            },
        },
        timeout=REQUEST_TIMEOUT_S,
    )

    print("========== GEMINI DEBUG ==========")
    print("Status Code:", response.status_code)
    print("Response:", response.text)
    print("==================================")

    response.raise_for_status()

    data = response.json()

        candidates = data.get("candidates") or []
        if not candidates:
            logger.warning("Gemini returned no candidates: %s", data)
            return None

        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts).strip()
        return text or None

    except requests.exceptions.RequestException as exc:
        logger.warning("Gemini API call failed: %s", exc)
        return None
    except (KeyError, IndexError, ValueError) as exc:
        logger.warning("Gemini response parsing failed: %s", exc)
        return None
