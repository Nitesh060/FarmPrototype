"""
ai_summary.py
Generates a human-readable farm analysis summary.
"""


def generate_summary(score, grade, satellite_data, crops):

    summary = []

    # Overall score
    summary.append(f"FarmScore: {score} ({grade})")

    # NDVI
    ndvi = satellite_data.get("ndvi", 0)

    if ndvi >= 0.70:
        summary.append("🌱 Vegetation is very healthy.")

    elif ndvi >= 0.50:
        summary.append("🌱 Vegetation is healthy.")

    elif ndvi >= 0.30:
        summary.append("🌱 Vegetation is moderate.")

    else:
        summary.append("🌱 Vegetation is poor.")

    # NDMI
    ndmi = satellite_data.get("ndmi", 0)

    if ndmi >= 0.20:
        summary.append("💧 Soil moisture is good.")
    elif ndmi >= 0:
        summary.append("💧 Soil moisture is moderate.")
    else:
        summary.append("💧 Soil moisture is low.")

    # Rainfall
    rainfall = satellite_data.get("rainfall", 0)

    if rainfall >= 6:
        summary.append("🌧 Rainfall is sufficient.")
    elif rainfall >= 3:
        summary.append("🌧 Rainfall is moderate.")
    else:
        summary.append("🌧 Rainfall is low.")

    # Temperature
    temp = satellite_data.get("temperature", 0)

    if 20 <= temp <= 32:
        summary.append("🌡 Temperature is suitable for farming.")
    else:
        summary.append("🌡 Temperature is less suitable for most crops.")

    # Groundwater
    gw = satellite_data.get("groundwater", 0)

    if gw >= 150:
        summary.append("🚰 Groundwater availability is good.")
    elif gw >= 80:
        summary.append("🚰 Groundwater availability is moderate.")
    else:
        summary.append("🚰 Groundwater availability is limited.")

    # Crop Recommendation
    if crops:
        summary.append(
            f"🌾 Recommended Crop: {crops['primary']['crop']}"
        )

    # Final Recommendation
    if grade == "Excellent":
        summary.append(
            "✅ Overall, this farm has excellent agricultural suitability."
        )

    elif grade == "Good":
        summary.append(
            "✅ Overall, this farm has good agricultural suitability."
        )

    elif grade == "Average":
        summary.append(
            "⚠ This farm has average agricultural suitability."
        )

    else:
        summary.append(
            "❌ Agricultural suitability is low. Field verification is recommended."
        )

    return summary
