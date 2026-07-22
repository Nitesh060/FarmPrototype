"""
gemini_service.py
==================
Generates a natural-language explanation of a FarmScore result using the
Gemini API — grounded strictly in the real numbers FarmScore already
computed.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash-lite"

GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

REQUEST_TIMEOUT_S = 12


def _build_prompt(context: Dict[str, Any]) -> str:
    components = context.get("components", {})

    lines = []
    for key, c in components.items():
        if not c:
            continue

        lines.append(
            f"- {key}: raw value {c.get('raw_value')} {c.get('unit') or ''}, "
            f"sub-score {c.get('sub_score')}/100, "
            f"weight {c.get('weight')}%, "
            f"source {c.get('source')}"
        )

    components_text = "\n".join(lines) or "No component data available."

    crop = context.get("recommended_crops") or {}
    primary_crop = crop.get("primary", {}).get("crop") if crop.get("primary") else None

    climate = context.get("climate_risk") or {}

    prompt = f"""
You are helping a bank loan officer read a farmland suitability report.

Below are the ACTUAL computed values.

Do NOT invent any values.

FarmScore:
{context.get('score')}/900 ({context.get('grade')})

Component breakdown:
{components_text}

Top recommended crop:
{primary_crop or "Not Available"}

Climate Risk:
{climate.get('level','Unknown')}

NDWI:
{context.get('ndwi')}

Write only 3-4 short sentences explaining the result.
"""

    return prompt


def generate_insight(context: Dict[str, Any]) -> Optional[str]:

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        print("❌ GEMINI_API_KEY NOT FOUND")
        return None

    prompt = _build_prompt(context)

    try:

        response = requests.post(
            GEMINI_URL,
            params={"key": api_key},
            json={
                "contents": [
                    {
                        "parts": [
                            {
                                "text": prompt
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 220
                }
            },
            timeout=REQUEST_TIMEOUT_S,
        )

        print("===================================")
        print("Gemini Status:", response.status_code)
        print("Gemini Body:", response.text)
        print("===================================")

        response.raise_for_status()

        data = response.json()

        candidates = data.get("candidates", [])

        if len(candidates) == 0:
            print("No candidates returned")
            return None

        parts = candidates[0]["content"]["parts"]

        text = "".join(
            part.get("text", "")
            for part in parts
        ).strip()

        return text if text else None

    except requests.exceptions.RequestException as e:
        print("Gemini Request Error:", e)

        if e.response is not None:
            print("Google Response:")
            print(e.response.text)

        return None

    except Exception as e:
        print("Gemini Unexpected Error:", e)
        return None
