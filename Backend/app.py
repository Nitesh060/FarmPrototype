"""
app.py
======
Flask REST API for the FarmScore agricultural-suitability platform.
"""

from __future__ import annotations

import logging
import os
import sys
import time

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

from earth_engine_service import fetch_farm_data, initialise_earth_engine
from scoring import calculate_score
from crop_recommendation import recommend_crop
from gemini_service import generate_insight

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
PORT = int(os.getenv("PORT", 5000))
HOST = os.getenv("HOST", "0.0.0.0")
DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})


@app.before_request
def _ensure_ee_init():
    try:
        initialise_earth_engine()
    except Exception as exc:
        logger.error("Earth Engine init failed: %s", exc)
        if request.endpoint != "health_check":
            raise


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "service": "FarmScore API"}), 200


@app.route("/calculate", methods=["POST"])
def calculate():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    lat = body.get("lat")
    lng = body.get("lng")
    polygon = body.get("polygon")

    if lat is None or lng is None:
        return jsonify({"error": "Both 'lat' and 'lng' are required"}), 400

    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return jsonify({"error": "'lat' and 'lng' must be numbers"}), 400

    if not (-90 <= lat <= 90):
        return jsonify({"error": f"Latitude out of range: {lat}"}), 400
    if not (-180 <= lng <= 180):
        return jsonify({"error": f"Longitude out of range: {lng}"}), 400

    t0 = time.time()
    logger.info("calculate lat=%.5f lng=%.5f", lat, lng)

    try:
        satellite_data = fetch_farm_data(lat=lat, lng=lng, polygon=polygon)
    except Exception as exc:
        logger.exception("Earth Engine fetch failed")
        return jsonify({"error": "Failed to retrieve satellite data", "detail": str(exc)}), 502

    try:
        result = calculate_score(
            ndvi=satellite_data.get("ndvi"),
            ndmi=satellite_data.get("ndmi"),
            rainfall=satellite_data.get("rainfall"),
            temperature=satellite_data.get("temperature"),
            groundwater=satellite_data.get("groundwater"),
        )
        crop_result = recommend_crop(
            satellite_data.get("ndvi"),
            satellite_data.get("ndmi"),
            satellite_data.get("rainfall"),
            satellite_data.get("temperature"),
            satellite_data.get("groundwater"),
        )
    except Exception as exc:
        logger.exception("Scoring computation failed")
        return jsonify({"error": "Scoring computation failed", "detail": str(exc)}), 500

    elapsed = round(time.time() - t0, 2)
    logger.info("Score=%d Grade=%s elapsed=%.2fs", result["final_score"], result["grade"], elapsed)

    # ---- Climate risk assessment — rule-based on the REAL rainfall/temperature
    # values just fetched, not a model prediction. Thresholds are simple and
    # transparent so the "why" is always visible. ----
    def _assess_climate_risk(rainfall_mm_day, temp_c):
        flags = []
        if rainfall_mm_day is not None:
            if rainfall_mm_day < 2:
                flags.append("Low rainfall for the growing season")
            elif rainfall_mm_day > 15:
                flags.append("Very high rainfall — waterlogging risk")
        if temp_c is not None:
            if temp_c > 35:
                flags.append("High temperature — heat stress risk")
            elif temp_c < 15:
                flags.append("Low temperature for most kharif crops")

        if not flags:
            level = "Low"
        elif len(flags) == 1:
            level = "Moderate"
        else:
            level = "High"

        return {"level": level, "flags": flags}

    climate_risk = _assess_climate_risk(
        satellite_data.get("rainfall"), satellite_data.get("temperature")
    )

    response_payload = {
        "score": result["final_score"],
        "grade": result["grade"],
        "components": result["components"],
        "recommended_crops": crop_result,
        "satellite_meta": satellite_data.get("satellite_meta"),
        "ndvi_trend": satellite_data.get("ndvi_trend"),
        "ndwi": satellite_data.get("ndwi"),
        "rainfall_monthly": satellite_data.get("rainfall_monthly"),
        "groundwater_trend": satellite_data.get("groundwater_trend"),
        "climate_risk": climate_risk,
        "coordinates": {"lat": lat, "lng": lng},
        "elapsed_seconds": elapsed,
    }

    # AI insight is generated from the payload above ONLY — grounded in
    # real, already-computed numbers. If it fails or no key is set, the
    # rest of the response is returned unaffected.
    try:
        ai_insight = generate_insight({**response_payload, "climate_risk": climate_risk})
    except Exception:
        logger.exception("AI insight generation failed (non-fatal)")
        ai_insight = None

    response_payload["ai_insight"] = ai_insight

    return jsonify(response_payload), 200


@app.errorhandler(404)
def not_found(_):
    return jsonify({"error": "Endpoint not found"}), 404


@app.errorhandler(405)
def method_not_allowed(_):
    return jsonify({"error": "Method not allowed"}), 405


@app.errorhandler(500)
def internal_error(_):
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    logger.info("Starting FarmScore API on %s:%d", HOST, PORT)
    app.run(host=HOST, port=PORT, debug=DEBUG)
