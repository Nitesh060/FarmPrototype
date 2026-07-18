"""
app.py
======
Flask REST API for the FarmScore agricultural-suitability platform.

Endpoints
---------
POST /calculate
    Accept ``{"lat": float, "lng": float}``, query Google Earth Engine
    for satellite data, compute the FarmScore, and return the result.

GET /health
    Lightweight health-check for load-balancers / uptime monitors.
"""

from __future__ import annotations

import logging
import os
import sys
import time

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

# ---------------------------------------------------------------------------
# Local modules
# ---------------------------------------------------------------------------
from earth_engine_service import fetch_farm_data, initialise_earth_engine
from scoring import calculate_score
from crop_recommendation import recommend_crop
# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
PORT = int(os.getenv("PORT", 5000))
HOST = os.getenv("HOST", "0.0.0.0")
DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})


# ---------------------------------------------------------------------------
# Eagerly initialise Earth Engine at startup
# ---------------------------------------------------------------------------
@app.before_request
def _ensure_ee_init():
    """Guarantee Earth Engine is initialised before the first request."""
    try:
        initialise_earth_engine()
    except Exception as exc:
        logger.error("Earth Engine init failed: %s", exc)
        # Allow health-check to still respond
        if request.endpoint != "health_check":
            raise


# ===================================================================
# Routes
# ===================================================================

@app.route("/health", methods=["GET"])
def health_check():
    """Lightweight health-check endpoint."""
    return jsonify({"status": "ok", "service": "FarmScore API"}), 200


@app.route("/calculate", methods=["POST"])
def calculate():
    """Calculate the FarmScore for a given coordinate.

    **Request body** (JSON)::

        {"lat": 20.29, "lng": 85.83}

    **Response** (JSON)::

        {
          "score": 220,
          "grade": "Good",
          "components": { … },
          "coordinates": {"lat": 20.29, "lng": 85.83},
          "elapsed_seconds": 12.4
        }
    """

    # ---- Parse input -------------------------------------------------------
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

    # ---- Fetch satellite data -----------------------------------------------
    t0 = time.time()
    logger.info("▶ /calculate  lat=%.5f  lng=%.5f", lat, lng)

    try:
        satellite_data = fetch_farm_data(
    lat=lat,
    lng=lng,
    polygon=polygon
)
    except Exception as exc:
        logger.exception("Earth Engine fetch failed")
        return jsonify({
            "error": "Failed to retrieve satellite data",
            "detail": str(exc),
        }), 502

    # ---- Compute score -------------------------------------------------------
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
        return jsonify({
            "error": "Scoring computation failed",
            "detail": str(exc),
        }), 500

    elapsed = round(time.time() - t0, 2)
    logger.info(
        "✓ Score=%d  Grade=%s  elapsed=%.2fs",
        result["final_score"], result["grade"], elapsed,
    )

    # ---- Return response -----------------------------------------------------
    return jsonify({
        "score": result["final_score"],
        "grade": result["grade"],
        "components": result["components"],
        "recommended_crops": crop_result,
        "coordinates": {"lat": lat, "lng": lng},
        "elapsed_seconds": elapsed,
    }), 200


# ===================================================================
# Error handlers
# ===================================================================

@app.errorhandler(404)
def not_found(_):
    return jsonify({"error": "Endpoint not found"}), 404


@app.errorhandler(405)
def method_not_allowed(_):
    return jsonify({"error": "Method not allowed"}), 405


@app.errorhandler(500)
def internal_error(_):
    return jsonify({"error": "Internal server error"}), 500


# ===================================================================
# Entry point
# ===================================================================

if __name__ == "__main__":
    logger.info("Starting FarmScore API on %s:%d", HOST, PORT)
    app.run(host=HOST, port=PORT, debug=DEBUG)
