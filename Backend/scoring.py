"""
scoring.py
==========
FarmScore scoring engine.

Accepts raw satellite-derived parameters and computes a weighted
agricultural-suitability index on a 300–900 scale.

Weights
-------
| Parameter       | Weight |
|-----------------|--------|
| Groundwater     | 25%    |
| NDVI            | 25%    |
| NDMI            | 20%    |
| Rainfall Score  | 10%    |
| Temperature Score | 20%  |

Formula
-------
    WeightedAvg = (25×GW + 25×NDVI_score + 20×NDMI_score
                   + 10×RainfallScore + 20×TempScore) / 100
    FinalScore  = round(300 + (WeightedAvg * 6))

Grade Bands
-----------
    781+ → Excellent
    661+ → Good
    541+ → Average
    421+ → Fair
    <421 → Poor
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WEIGHTS = {
    "groundwater": 25,
    "ndvi": 25,
    "ndmi": 20,
    "rainfall": 10,
    "temperature": 20,
}

GRADE_BANDS = [
    (781, "Excellent"),
    (661, "Good"),
    (541, "Average"),
    (421, "Fair"),
]

DEFAULT_GRADE = "Poor"

# Benchmark references used in sub-score normalisation
RAINFALL_BENCHMARK_MM = 5.0   # ideal daily rainfall (mm/day)
TEMP_BENCHMARK_C = 30.0       # ideal max temperature (°C)


# ---------------------------------------------------------------------------
# Sub-score helpers
# ---------------------------------------------------------------------------

def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp *value* between *lo* and *hi*."""
    return max(lo, min(hi, value))


def _rainfall_score(rainfall_mm_per_day: float) -> float:
    """Convert mean daily rainfall (mm/day) to a 0–100 score.

    Score = 100 − 100 × |benchmark − P| / benchmark
    Perfect score when P == benchmark (5 mm/day).
    """
    deviation = abs(RAINFALL_BENCHMARK_MM - rainfall_mm_per_day)
    score = 100.0 - 100.0 * deviation / RAINFALL_BENCHMARK_MM
    return _clamp(score)


def _temperature_score(temperature_c: float) -> float:
    """Convert mean temperature (°C) to a 0–100 score.

    Score = 100 − 100 × |benchmark − T| / benchmark
    Perfect score when T == benchmark (30 °C).
    """
    deviation = abs(TEMP_BENCHMARK_C - temperature_c)
    score = 100.0 - 100.0 * deviation / TEMP_BENCHMARK_C
    return _clamp(score)


def _ndvi_score(ndvi: float) -> float:
    """Scale NDVI (typically −1 to 1) into a 0–100 score.

    NDVI × 100 — negative values clamp to 0.
    """
    return _clamp(ndvi * 100.0)


def _ndmi_score(ndmi: float) -> float:
    """Scale NDMI (typically −1 to 1) into a 0–100 score.

    NDMI × 100 — negative values clamp to 0.
    """
    return _clamp(ndmi * 100.0)


def _groundwater_score(groundwater_raw: float) -> float:
    """Normalise groundwater proxy (kg/m², typically 50–500) to 0–100.

    Uses the raw value divided by 10 as the score input, then clamps.
    GW values from GLDAS SoilMoi100_200cm are typically 50–450 kg/m².
    Score = GW / 5  (maps 0→0, 250→50, 500→100).
    """
    return _clamp(groundwater_raw / 5.0)


# ---------------------------------------------------------------------------
# Grade assignment
# ---------------------------------------------------------------------------

def _assign_grade(final_score: int) -> str:
    """Return a grade string based on the final score."""
    for threshold, label in GRADE_BANDS:
        if final_score >= threshold:
            return label
    return DEFAULT_GRADE


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calculate_score(
    ndvi: Optional[float],
    ndmi: Optional[float],
    rainfall: Optional[float],
    temperature: Optional[float],
    groundwater: Optional[float],
) -> Dict[str, Any]:
    """Compute the FarmScore from raw satellite parameters.

    Parameters
    ----------
    ndvi : float or None
        Mean NDVI (−1 to 1).
    ndmi : float or None
        Mean NDMI (−1 to 1).
    rainfall : float or None
        Mean daily precipitation (mm/day).
    temperature : float or None
        Mean land-surface temperature (°C).
    groundwater : float or None
        Mean deep soil moisture (kg/m²).

    Returns
    -------
    dict
        ``final_score`` (int 300–900), ``grade`` (str),
        ``components`` (dict with per-parameter breakdown).

    Notes
    -----
    If a parameter is ``None`` (no data available), a safe default of 0
    is used for that sub-score and the component is flagged.
    """

    # ---- Resolve None → 0 with flag ----
    def _safe(val: Optional[float], default: float = 0.0) -> tuple[float, bool]:
        if val is None:
            return default, False
        return float(val), True

    ndvi_val, ndvi_ok = _safe(ndvi)
    ndmi_val, ndmi_ok = _safe(ndmi)
    rain_val, rain_ok = _safe(rainfall)
    temp_val, temp_ok = _safe(temperature)
    gw_val, gw_ok = _safe(groundwater)

    # ---- Compute sub-scores ----
    gw_sc = _groundwater_score(gw_val)
    ndvi_sc = _ndvi_score(ndvi_val)
    ndmi_sc = _ndmi_score(ndmi_val)
    rain_sc = _rainfall_score(rain_val)
    temp_sc = _temperature_score(temp_val)

    # ---- Weighted average ----
    weighted_avg = (
        WEIGHTS["groundwater"] * gw_sc
        + WEIGHTS["ndvi"] * ndvi_sc
        + WEIGHTS["ndmi"] * ndmi_sc
        + WEIGHTS["rainfall"] * rain_sc
        + WEIGHTS["temperature"] * temp_sc
    ) / 100.0

    # Map 0-100 scale to 300-900 scale
    # F = 300 + W * (900 - 300) / 100 = 300 + W * 6
    final_score = round(300 + (weighted_avg * 6.0))
    final_score = max(300, min(900, final_score))

    grade = _assign_grade(final_score)

    logger.info(
        "FarmScore computed: %d (%s)  |  GW=%.1f  NDVI=%.1f  NDMI=%.1f  "
        "Rain=%.1f  Temp=%.1f",
        final_score, grade, gw_sc, ndvi_sc, ndmi_sc, rain_sc, temp_sc,
    )

    return {
        "final_score": final_score,
        "grade": grade,
        "components": {
            "groundwater": {
                "raw_value": gw_val,
                "sub_score": round(gw_sc, 2),
                "weight": WEIGHTS["groundwater"],
                "weighted_contribution": round(gw_sc * WEIGHTS["groundwater"] / 100, 2),
                "data_available": gw_ok,
                "unit": "kg/m²",
                "source": "NASA GLDAS",
            },
            "ndvi": {
                "raw_value": round(ndvi_val, 6),
                "sub_score": round(ndvi_sc, 2),
                "weight": WEIGHTS["ndvi"],
                "weighted_contribution": round(ndvi_sc * WEIGHTS["ndvi"] / 100, 2),
                "data_available": ndvi_ok,
                "unit": "",
                "source": "Sentinel-2",
            },
            "ndmi": {
                "raw_value": round(ndmi_val, 6),
                "sub_score": round(ndmi_sc, 2),
                "weight": WEIGHTS["ndmi"],
                "weighted_contribution": round(ndmi_sc * WEIGHTS["ndmi"] / 100, 2),
                "data_available": ndmi_ok,
                "unit": "",
                "source": "Sentinel-2",
            },
            "rainfall": {
                "raw_value": round(rain_val, 4),
                "sub_score": round(rain_sc, 2),
                "weight": WEIGHTS["rainfall"],
                "weighted_contribution": round(rain_sc * WEIGHTS["rainfall"] / 100, 2),
                "data_available": rain_ok,
                "unit": "mm/day",
                "source": "CHIRPS",
            },
            "temperature": {
                "raw_value": round(temp_val, 4),
                "sub_score": round(temp_sc, 2),
                "weight": WEIGHTS["temperature"],
                "weighted_contribution": round(temp_sc * WEIGHTS["temperature"] / 100, 2),
                "data_available": temp_ok,
                "unit": "°C",
                "source": "MODIS LST",
            },
        },
    }
