"""
Rule-based farm analysis agent for stored sensor history.

This intentionally has no external AI dependency, so recommendations keep
working on ESP32 uploads even when there is no LLM key configured.
"""

from datetime import datetime
import json


def _values(readings, attr):
    return [getattr(reading, attr) for reading in readings if getattr(reading, attr) is not None]


def _avg(readings, attr):
    values = _values(readings, attr)
    return round(sum(values) / len(values), 2) if values else None


def _trend(readings, attr):
    values = _values(readings, attr)
    if len(values) < 4:
        return "stable"
    midpoint = max(1, len(values) // 2)
    older = values[midpoint:]
    newer = values[:midpoint]
    if not older or not newer:
        return "stable"
    delta = (sum(newer) / len(newer)) - (sum(older) / len(older))
    if delta > 3:
        return "rising"
    if delta < -3:
        return "falling"
    return "stable"


def analyze_sensor_history(readings, plant_type=None):
    """Return prioritized recommendations from newest-first readings."""
    summary = {
        "sample_count": len(readings),
        "plant_type": plant_type,
        "temperature_avg": _avg(readings, "temperature"),
        "humidity_avg": _avg(readings, "humidity"),
        "soil_moisture_avg": _avg(readings, "soil_moisture"),
        "mq135_avg": _avg(readings, "mq135_reading"),
        "light_avg": _avg(readings, "light_intensity"),
        "soil_moisture_trend": _trend(readings, "soil_moisture"),
        "temperature_trend": _trend(readings, "temperature"),
        "analyzed_at": datetime.utcnow().isoformat(),
    }

    recommendations = []
    soil = summary["soil_moisture_avg"]
    temp = summary["temperature_avg"]
    humidity = summary["humidity_avg"]
    air = summary["mq135_avg"]
    light = summary["light_avg"]

    if soil is not None and soil < 30:
        recommendations.append({
            "title": "Increase watering",
            "priority": "high",
            "reason": f"Soil moisture average is {soil}%, below the 30% safe threshold.",
            "action": "Run the pump, then recheck moisture after 10-15 minutes.",
        })
    elif soil is not None and soil > 75:
        recommendations.append({
            "title": "Reduce irrigation",
            "priority": "medium",
            "reason": f"Soil moisture average is {soil}%, which can stress roots.",
            "action": "Pause automatic watering and inspect drainage.",
        })

    if temp is not None and temp > 35:
        recommendations.append({
            "title": "Cool the growing area",
            "priority": "high",
            "reason": f"Temperature average is {temp} C.",
            "action": "Improve ventilation, shade the area, or reduce grow-light heat.",
        })
    elif temp is not None and temp < 16:
        recommendations.append({
            "title": "Raise canopy temperature",
            "priority": "medium",
            "reason": f"Temperature average is {temp} C.",
            "action": "Add gentle heat or adjust the light cycle.",
        })

    if humidity is not None and humidity < 40:
        recommendations.append({
            "title": "Increase humidity",
            "priority": "medium",
            "reason": f"Humidity average is {humidity}%.",
            "action": "Mist the area or reduce exhaust fan speed for a short interval.",
        })
    elif humidity is not None and humidity > 85:
        recommendations.append({
            "title": "Lower humidity",
            "priority": "medium",
            "reason": f"Humidity average is {humidity}%, increasing fungal disease risk.",
            "action": "Increase airflow and avoid watering leaves.",
        })

    if air is not None and air > 400:
        recommendations.append({
            "title": "Improve air quality",
            "priority": "high",
            "reason": f"MQ-135 average is {air}.",
            "action": "Check ventilation, gas sources, and sensor calibration.",
        })

    if light is not None and light < 300:
        recommendations.append({
            "title": "Increase light exposure",
            "priority": "medium",
            "reason": f"Light average is {light} lux.",
            "action": "Turn on the grow light or extend the photoperiod.",
        })

    if not recommendations:
        recommendations.append({
            "title": "Maintain current settings",
            "priority": "low",
            "reason": "Recent readings are inside the expected operating range.",
            "action": "Keep monitoring trends and inspect plants visually once per day.",
        })

    return {
        "summary": summary,
        "recommendations": recommendations,
        "summary_json": json.dumps(summary),
    }
