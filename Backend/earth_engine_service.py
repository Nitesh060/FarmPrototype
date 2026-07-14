"""
earth_engine_service.py
========================
Production-ready Google Earth Engine data-retrieval service for FarmScore.

Authenticates with a GEE service account, then queries five satellite /
reanalysis datasets for a single point location over the Aug–Oct growing
seasons of 2020-2023.

Datasets
--------
| Parameter    | Dataset ID                                      | Band(s)                  |
|--------------|-------------------------------------------------|--------------------------|
| NDVI         | COPERNICUS/S2_SR_HARMONIZED                     | B8, B4                   |
| NDMI         | COPERNICUS/S2_SR_HARMONIZED                     | B8, B11                  |
| Rainfall     | UCSB-CHG/CHIRPS/DAILY                           | precipitation            |
| Temperature  | MODIS/061/MOD11A1                               | LST_Day_1km              |
| Groundwater  | NASA/GLDAS/V021/NOAH/G025/T3H                  | SoilMoi100_200cm_inst    |
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

import ee

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level initialisation guard
# ---------------------------------------------------------------------------
_ee_initialised = False
_init_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
START_DATE = "2020-08-01"
END_DATE = "2023-10-31"

# Growing-season months (August = 8 … October = 10)
SEASON_MONTHS = [8, 9, 10]

# Default buffer radius (metres) around the queried point — keeps reducers
# from returning null on sparse datasets.
BUFFER_RADIUS_M = 1000

# Maximum cloud cover percentage for Sentinel-2 scenes
S2_MAX_CLOUD_PCT = 30

# In-memory cache for coordinates to avoid redundant Earth Engine calls.
# Cache key is rounded to 5 decimal places: (round(lat, 5), round(lng, 5))
_coord_cache: Dict[tuple[float, float], Dict[str, Optional[float]]] = {}
_cache_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def _resolve_credentials_path() -> str:
    """Return the absolute path to the GEE service-account key file.

    Resolution order:
      1. ``GEE_KEY_FILE`` environment variable (explicit override).
      2. ``credentials/gee-service-account.json`` relative to this file.

    Raises ``FileNotFoundError`` if neither resolves to an existing file.
    """
    env_path = os.getenv("GEE_KEY_FILE")
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return str(p)
        raise FileNotFoundError(
            f"GEE_KEY_FILE points to a non-existent file: {env_path}"
        )

    default_path = Path(__file__).resolve().parent / "credentials" / "gee-service-account.json"
    if default_path.is_file():
        return str(default_path)

    raise FileNotFoundError(
        "Service-account key not found. Set GEE_KEY_FILE or place the key at "
        f"{default_path}"
    )


def initialise_earth_engine() -> None:
    """Initialise Earth Engine with service-account credentials (idempotent).

    Thread-safe — multiple concurrent Flask requests will not race.
    """
    global _ee_initialised
    if _ee_initialised:
        return

    with _init_lock:
        if _ee_initialised:          # double-checked locking
            return

        credentials_json = os.getenv("GOOGLE_CREDENTIALS")

        if credentials_json:
            import tempfile

            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tmp:
                tmp.write(credentials_json)
                key_path = tmp.name
        else:
            key_path = _resolve_credentials_path()

        logger.info("Authenticating Earth Engine with key: %s", key_path)

        with open(key_path, "r", encoding="utf-8") as fh:
            key_data = json.load(fh)

        service_account = key_data.get("client_email")
        if not service_account:
            raise ValueError("client_email missing from service-account key file")

        credentials = ee.ServiceAccountCredentials(service_account, key_path)
        ee.Initialize(credentials)
        logger.info("Earth Engine initialised for account: %s", service_account)
        _ee_initialised = True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _point_geometry(lat: float, lng: float) -> ee.Geometry.Point:
    """Create an ``ee.Geometry.Point`` (longitude first, as GEE expects)."""
    return ee.Geometry.Point([lng, lat])


def _buffered_region(lat: float, lng: float, radius_m: int = BUFFER_RADIUS_M) -> ee.Geometry:
    """Return a circular buffer around the point to guard against sparse pixels."""
    return _point_geometry(lat, lng).buffer(radius_m)


def _filter_growing_season(collection: ee.ImageCollection) -> ee.ImageCollection:
    """Restrict an ImageCollection to calendar months 8-10 across all years."""
    return collection.filter(ee.Filter.calendarRange(8, 10, "month"))


def _reduce_mean(image: ee.Image, region: ee.Geometry, scale: int) -> Optional[float]:
    """Reduce an image to its mean value over *region* at the given scale.

    Returns ``None`` if the reducer yields no data (e.g. ocean pixels).
    """
    result: Dict[str, Any] = (
        image
        .reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=region,
            scale=scale,
            maxPixels=1e9,
        )
        .getInfo()
    )
    # Return the first non-null value found
    for val in result.values():
        if val is not None:
            return float(val)
    return None


# ---------------------------------------------------------------------------
# Dataset fetch functions
# ---------------------------------------------------------------------------

def _fetch_s2_indices(lat: float, lng: float) -> tuple[Optional[float], Optional[float]]:
    """Mean NDVI and NDMI from Sentinel-2 Surface Reflectance (Harmonized) in a single query.

    NDVI = (B8 – B4) / (B8 + B4)
    NDMI = (B8 – B11) / (B8 + B11)
    """
    region = _buffered_region(lat, lng)
    s2 = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterDate(START_DATE, END_DATE)
        .filterBounds(region)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", S2_MAX_CLOUD_PCT))
    )
    s2 = _filter_growing_season(s2)

    def compute_indices(img: ee.Image) -> ee.Image:
        ndvi = img.normalizedDifference(["B8", "B4"]).rename("NDVI")
        ndmi = img.normalizedDifference(["B8", "B11"]).rename("NDMI")
        return img.addBands([ndvi, ndmi])

    indices_collection = s2.map(compute_indices)
    mean_indices = indices_collection.select(["NDVI", "NDMI"]).mean()

    # Perform a single reduceRegion call for both bands
    result = (
        mean_indices
        .reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=region,
            scale=10,
            maxPixels=1e9,
        )
        .getInfo()
    )

    ndvi_val = float(result["NDVI"]) if result and result.get("NDVI") is not None else None
    ndmi_val = float(result["NDMI"]) if result and result.get("NDMI") is not None else None
    return ndvi_val, ndmi_val


def _fetch_rainfall(lat: float, lng: float) -> Optional[float]:
    """Mean daily precipitation (mm/day) from CHIRPS Daily dataset.

    Returns the temporal mean of daily precipitation values over the
    growing-season windows.
    """
    region = _buffered_region(lat, lng)
    chirps = (
        ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
        .filterDate(START_DATE, END_DATE)
        .filterBounds(region)
        .select("precipitation")
    )
    chirps = _filter_growing_season(chirps)

    mean_precip = chirps.mean()
    return _reduce_mean(mean_precip, region, scale=5566)


def _fetch_temperature(lat: float, lng: float) -> Optional[float]:
    """Mean daytime Land Surface Temperature (°C) from MODIS/061/MOD11A1.

    The raw band stores LST in Kelvin × 0.02.  We apply the scale factor
    and convert to Celsius.
    """
    region = _buffered_region(lat, lng)
    modis = (
        ee.ImageCollection("MODIS/061/MOD11A1")
        .filterDate(START_DATE, END_DATE)
        .filterBounds(region)
        .select("LST_Day_1km")
    )
    modis = _filter_growing_season(modis)

    # Scale: DN × 0.02 → Kelvin, then K – 273.15 → °C
    lst_celsius = modis.map(
        lambda img: img.multiply(0.02).subtract(273.15).rename("LST_C")
    )
    mean_lst = lst_celsius.mean()
    return _reduce_mean(mean_lst, region, scale=1000)


def _fetch_groundwater(lat: float, lng: float) -> Optional[float]:
    """Mean deep-layer soil moisture (kg/m²) from GLDAS Noah v2.1.

    Uses ``SoilMoi100_200cm_inst`` (100-200 cm layer) as a proxy for
    groundwater storage.
    """
    region = _buffered_region(lat, lng)
    gldas = (
        ee.ImageCollection("NASA/GLDAS/V021/NOAH/G025/T3H")
        .filterDate(START_DATE, END_DATE)
        .filterBounds(region)
        .select("SoilMoi100_200cm_inst")
    )
    gldas = _filter_growing_season(gldas)

    mean_gw = gldas.mean()
    return _reduce_mean(mean_gw, region, scale=27830)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_farm_data(lat: float, lng: float) -> Dict[str, Optional[float]]:
    """Fetch all five agricultural parameters for a single coordinate.

    Parameters
    ----------
    lat : float
        Latitude in decimal degrees (−90 to 90).
    lng : float
        Longitude in decimal degrees (−180 to 180).

    Returns
    -------
    dict
        Keys: ``ndvi``, ``ndmi``, ``rainfall``, ``temperature``,
        ``groundwater``.  Values are floats or ``None`` when no data
        is available for that parameter at the queried location.

    Raises
    ------
    ValueError
        If the coordinates are out of range.
    RuntimeError
        If Earth Engine has not been initialised.
    """
    # ---- Validate inputs ----
    if not (-90 <= lat <= 90):
        raise ValueError(f"Latitude out of range: {lat}")
    if not (-180 <= lng <= 180):
        raise ValueError(f"Longitude out of range: {lng}")

    # ---- Check Cache ----
    cache_key = (round(lat, 5), round(lng, 5))
    with _cache_lock:
        if cache_key in _coord_cache:
            logger.info("Cache hit for coordinates: %s -> %s", (lat, lng), cache_key)
            return _coord_cache[cache_key].copy()

    # ---- Ensure EE is ready ----
    initialise_earth_engine()

    # ---- Fetch each parameter ----
    logger.info("Fetching Earth Engine data for (%.5f, %.5f) …", lat, lng)

    ndvi, ndmi = _fetch_s2_indices(lat, lng)
    logger.debug("  NDVI:         %s", ndvi)
    logger.debug("  NDMI:         %s", ndmi)

    rainfall = _fetch_rainfall(lat, lng)
    logger.debug("  Rainfall:     %s mm/day", rainfall)

    temperature = _fetch_temperature(lat, lng)
    logger.debug("  Temperature:  %s °C", temperature)

    groundwater = _fetch_groundwater(lat, lng)
    logger.debug("  Groundwater:  %s kg/m²", groundwater)

    result = {
        "ndvi": round(ndvi, 6) if ndvi is not None else None,
        "ndmi": round(ndmi, 6) if ndmi is not None else None,
        "rainfall": round(rainfall, 4) if rainfall is not None else None,
        "temperature": round(temperature, 4) if temperature is not None else None,
        "groundwater": round(groundwater, 4) if groundwater is not None else None,
    }

    with _cache_lock:
        _coord_cache[cache_key] = result

    return result.copy()
