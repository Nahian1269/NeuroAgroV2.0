"""
Weather prediction and crop-advice helpers for NuroAgro.

The service attempts to use the supplied Transformer model and scaler when
TensorFlow/Keras and the scaler dependencies are installed. If not, the app
keeps running with a deterministic local fallback so dashboards and APIs stay
usable during development.
"""

from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timedelta
from statistics import mean

import joblib
import numpy as np
import requests
from dotenv import load_dotenv


load_dotenv()

WEATHER_FIELDS = [
    "max_temperature",
    "min_temperature",
    "apparent_temperature",
    "humidity",
    "pressure",
    "rainfall",
]

FEATURE_FIELDS = [
    "temperature",
    "humidity",
    "soil_moisture",
    "light_intensity",
    "rain_level",
    "water_level",
]

MODEL_FILE = os.environ.get("WEATHER_MODEL_PATH", "weather_prediction_transformer_model.keras")
SCALER_FILE = os.environ.get("WEATHER_SCALER_PATH", "scaler.pkl")
CALIBRATION_FILE = os.environ.get("WEATHER_CALIBRATION_PATH", "weather_calibration.json")

_MODEL = None
_MODEL_ERROR = None
_SCALER = None
_SCALER_ERROR = None
_CALIBRATION = None


def _round(value, digits=2):
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _record_value(record, field, default=0.0):
    value = getattr(record, field, None)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_model():
    global _MODEL, _MODEL_ERROR
    if _MODEL is not None or _MODEL_ERROR is not None:
        return _MODEL

    try:
        from tensorflow import keras

        class TransformerBlock(keras.layers.Layer):
            def __init__(self, embed_dim, num_heads, ff_dim, rate=0.1, **kwargs):
                super().__init__(**kwargs)
                self.embed_dim = embed_dim
                self.num_heads = num_heads
                self.ff_dim = ff_dim
                self.rate = rate
                self.att = keras.layers.MultiHeadAttention(num_heads=num_heads, key_dim=embed_dim)
                self.ffn = keras.Sequential([
                    keras.layers.Dense(ff_dim, activation="relu"),
                    keras.layers.Dense(embed_dim),
                ])
                self.layernorm1 = keras.layers.LayerNormalization(epsilon=1e-6)
                self.layernorm2 = keras.layers.LayerNormalization(epsilon=1e-6)
                self.dropout1 = keras.layers.Dropout(rate)
                self.dropout2 = keras.layers.Dropout(rate)

            def call(self, inputs, training=False):
                attn_output = self.att(inputs, inputs)
                attn_output = self.dropout1(attn_output, training=training)
                out1 = self.layernorm1(inputs + attn_output)
                ffn_output = self.ffn(out1)
                ffn_output = self.dropout2(ffn_output, training=training)
                return self.layernorm2(out1 + ffn_output)

            def get_config(self):
                config = super().get_config()
                config.update({
                    "embed_dim": self.embed_dim,
                    "num_heads": self.num_heads,
                    "ff_dim": self.ff_dim,
                    "rate": self.rate,
                })
                return config

        _MODEL = keras.models.load_model(
            MODEL_FILE,
            compile=False,
            custom_objects={"TransformerBlock": TransformerBlock},
        )
    except Exception as exc:
        _MODEL_ERROR = str(exc)
        _MODEL = None
    return _MODEL


def _load_scaler():
    global _SCALER, _SCALER_ERROR
    if _SCALER is not None or _SCALER_ERROR is not None:
        return _SCALER

    try:
        sys.modules.setdefault("numpy._core", np.core)
        sys.modules.setdefault("numpy._core.multiarray", np.core.multiarray)
        sys.modules.setdefault("numpy._core.numeric", np.core.numeric)
        _SCALER = joblib.load(SCALER_FILE)
    except Exception as exc:
        _SCALER_ERROR = str(exc)
        _SCALER = None
    return _SCALER


def _load_calibration():
    global _CALIBRATION
    if _CALIBRATION is not None:
        return _CALIBRATION

    try:
        with open(CALIBRATION_FILE, "r", encoding="utf-8") as handle:
            _CALIBRATION = json.load(handle)
    except Exception:
        _CALIBRATION = {}
    return _CALIBRATION


def _save_calibration(payload):
    global _CALIBRATION
    _CALIBRATION = payload
    try:
        with open(CALIBRATION_FILE, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
    except Exception:
        payload["write_status"] = "calibration_file_not_writable"


def model_status():
    model = _load_model()
    scaler = _load_scaler()
    if model is not None:
        return "transformer_model_loaded" if scaler is not None else "transformer_loaded_without_scaler"
    if _MODEL_ERROR:
        return f"fallback_prediction: {_MODEL_ERROR[:90]}"
    return "fallback_prediction"


def _feature_window(readings, project=None, window_size=24):
    items = list(readings or [])[:window_size]
    items.reverse()

    if not items:
        base = [24.0, 55.0, 45.0, 650.0, 0.0, 70.0]
        items = [None] * window_size
    else:
        latest = items[-1]
        base = [
            _record_value(latest, "temperature", 24.0),
            _record_value(latest, "humidity", 55.0),
            _record_value(latest, "soil_moisture", 45.0),
            _record_value(latest, "light_intensity", 650.0),
            _record_value(latest, "rain_level", 0.0),
            _record_value(latest, "water_level", 70.0),
        ]

    rows = []
    for item in items[-window_size:]:
        if item is None:
            rows.append(base)
        else:
            rows.append([
                _record_value(item, "temperature", base[0]),
                _record_value(item, "humidity", base[1]),
                _record_value(item, "soil_moisture", base[2]),
                _record_value(item, "light_intensity", base[3]),
                _record_value(item, "rain_level", base[4]),
                _record_value(item, "water_level", base[5]),
            ])

    while len(rows) < window_size:
        rows.insert(0, rows[0] if rows else base)

    return np.array(rows[-window_size:], dtype=float)


def _transform_features(window):
    scaler = _load_scaler()
    if scaler is None or not hasattr(scaler, "transform"):
        return window

    flat = window.reshape(-1, window.shape[-1])
    try:
        scaled = scaler.transform(flat)
        return np.array(scaled, dtype=float).reshape(window.shape)
    except Exception:
        return window


def _inverse_scale_prediction(values):
    scaler = _load_scaler()
    if scaler is None or not hasattr(scaler, "inverse_transform"):
        return values

    try:
        arr = np.array(values, dtype=float).reshape(1, -1)
        expected_features = getattr(scaler, "n_features_in_", arr.shape[1])
        if arr.shape[1] != expected_features:
            return values
        return scaler.inverse_transform(arr).reshape(-1)
    except Exception:
        return values


def _model_prediction(window):
    model = _load_model()
    if model is None:
        return None

    model_input = _transform_features(window)
    try:
        input_shape = getattr(model, "input_shape", None)
        if isinstance(input_shape, list):
            input_shape = input_shape[0]

        if input_shape and len(input_shape) == 2:
            payload = model_input[-1:].reshape(1, -1)
        elif input_shape and len(input_shape) == 3:
            expected_steps = input_shape[1] or model_input.shape[0]
            expected_features = input_shape[2] or model_input.shape[1]
            window = model_input[:, :expected_features]
            if window.shape[0] < expected_steps:
                pad = np.repeat(window[:1], expected_steps - window.shape[0], axis=0)
                window = np.vstack([pad, window])
            payload = window[-expected_steps:, :expected_features].reshape(1, expected_steps, expected_features)
        else:
            payload = model_input.reshape(1, model_input.shape[0], model_input.shape[1])

        prediction = np.array(model.predict(payload, verbose=0)).reshape(-1)
        if prediction.size < len(WEATHER_FIELDS):
            return None
        return _inverse_scale_prediction(prediction[:len(WEATHER_FIELDS)])
    except Exception:
        return None


def _fallback_prediction(readings, horizon_minutes=30):
    latest = list(readings or [])[:1]
    latest = latest[0] if latest else None
    now = datetime.utcnow()
    hour_angle = (now.hour + horizon_minutes / 60) / 24 * math.tau
    temperature = _record_value(latest, "temperature", 24.0)
    humidity = _record_value(latest, "humidity", 55.0)
    rain_level = _record_value(latest, "rain_level", 0.0)
    light = _record_value(latest, "light_intensity", 650.0)

    swing = 4.5 + max(0, min(light, 1500)) / 1200
    max_temperature = temperature + max(0.5, math.sin(hour_angle) * swing + 1.8)
    min_temperature = temperature - swing - 1.2
    apparent_temperature = max_temperature + ((humidity - 50) / 35)
    pressure = 1013.25 + (50 - humidity) * 0.025 - (temperature - 22) * 0.18
    rainfall = max(0, rain_level * 0.42)

    return np.array([
        max_temperature,
        min_temperature,
        apparent_temperature,
        humidity,
        pressure,
        rainfall,
    ])


def predict_weather(readings, project=None, horizon_minutes=30):
    window = _feature_window(readings, project)
    prediction = _model_prediction(window)
    used_model = prediction is not None
    if prediction is None:
        prediction = _fallback_prediction(readings, horizon_minutes)

    payload = {
        WEATHER_FIELDS[index]: _round(prediction[index])
        for index in range(len(WEATHER_FIELDS))
    }
    calibration = _load_calibration()
    offsets = calibration.get("offsets", {}) if isinstance(calibration, dict) else {}
    if offsets:
        for field in WEATHER_FIELDS:
            if payload.get(field) is not None and offsets.get(field) is not None:
                payload[field] = _round(float(payload[field]) + float(offsets[field]))

    payload.update({
        "source": "transformer" if used_model else "fallback",
        "model_status": f"{model_status()}+calibrated" if offsets else model_status(),
        "model_available": used_model,
        "confidence": min(97.0, (86.0 if used_model else 62.0) + (4.0 if offsets else 0.0)),
        "horizon_minutes": horizon_minutes,
        "forecast_for": (datetime.utcnow() + timedelta(minutes=horizon_minutes)).isoformat(),
        "calibration": calibration if offsets else {},
    })
    return payload


def summarize_weather(records):
    rows = [record.to_dict() if hasattr(record, "to_dict") else record for record in records or []]
    summary = {}
    for field in WEATHER_FIELDS:
        values = [row.get(field) for row in rows if row.get(field) is not None]
        summary[field] = _round(mean(values), 2) if values else None
    summary["sample_count"] = len(rows)
    return summary


def _local_crop_advice(weather_payload, three_month_summary, project=None, plant_type=None):
    humidity = weather_payload.get("humidity") or three_month_summary.get("humidity") or 55
    max_temp = weather_payload.get("max_temperature") or three_month_summary.get("max_temperature") or 24
    rainfall = weather_payload.get("rainfall") or three_month_summary.get("rainfall") or 0
    water_system = getattr(project, "water_system", None) or "hybrid"

    if max_temp < 20:
        plants = ["Spinach", "Lettuce", "Mint", "Pak choi"]
    elif max_temp > 31:
        plants = ["Okra", "Basil", "Cucumber", "Amaranth"]
    elif humidity > 70 or rainfall > 18:
        plants = ["Basil", "Mint", "Lettuce", "Cucumber"]
    else:
        plants = ["Tomato", "Strawberry", "Lettuce", "Basil"]

    if water_system in {"hydroponic", "aquaponic", "aeroponic", "hybrid"}:
        plants = ["Lettuce", "Basil", "Spinach", *[plant for plant in plants if plant not in {"Lettuce", "Basil", "Spinach"}]]

    selected = plants[:5]
    return {
        "summary": (
            f"Next 30 minutes: max {weather_payload.get('max_temperature')} C, "
            f"min {weather_payload.get('min_temperature')} C, humidity {weather_payload.get('humidity')}%, "
            f"rainfall {weather_payload.get('rainfall')} mm. For a 3-month crop plan, prioritize "
            f"{', '.join(selected[:3])}."
        ),
        "plants": selected,
        "source": "local_agent",
    }


def _extract_openai_text(response_json):
    if response_json.get("output_text"):
        return response_json["output_text"]

    chunks = []
    for item in response_json.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if text:
                chunks.append(text)
    return "\n".join(chunks).strip()


def chatgpt_crop_advice(weather_payload, three_month_summary, project=None, plant_type=None):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return _local_crop_advice(weather_payload, three_month_summary, project, plant_type)

    model = os.environ.get("OPENAI_MODEL", "gpt-5.1-mini")
    prompt = {
        "current_prediction": weather_payload,
        "three_month_weather_summary": three_month_summary,
        "project": {
            "name": getattr(project, "project_name", None),
            "area_sq_ft": getattr(project, "land_area", None),
            "water_system": getattr(project, "water_system", None),
            "vertical_stories": getattr(project, "vertical_stories", None),
        },
        "current_crop": plant_type,
    }

    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "instructions": (
                    "You are NuroAgro's agronomy assistant. Return concise JSON with keys "
                    "summary and plants. plants must be a list of 3-6 crop names suitable for "
                    "the next 3 months based on the weather data."
                ),
                "input": json.dumps(prompt),
                "max_output_tokens": 500,
            },
            timeout=20,
        )
        response.raise_for_status()
        text = _extract_openai_text(response.json())
        try:
            parsed = json.loads(text)
            return {
                "summary": parsed.get("summary") or text,
                "plants": parsed.get("plants") or [],
                "source": "chatgpt",
            }
        except Exception:
            local = _local_crop_advice(weather_payload, three_month_summary, project, plant_type)
            local["summary"] = text or local["summary"]
            local["source"] = "chatgpt_text"
            return local
    except Exception as exc:
        fallback = _local_crop_advice(weather_payload, three_month_summary, project, plant_type)
        fallback["source"] = "local_agent_after_chatgpt_error"
        fallback["error"] = str(exc)
        return fallback


def evaluate_weather_training(records):
    predicted = [record for record in records if getattr(record, "source", None) == "predicted"]
    realtime = [record for record in records if getattr(record, "source", None) == "realtime"]

    if len(predicted) < 2 or len(realtime) < 2:
        return {
            "status": "insufficient_data",
            "samples_count": min(len(predicted), len(realtime)),
            "accuracy_score": None,
            "mean_absolute_error": None,
            "details": {
                "message": "Need both predicted and realtime weather history to calibrate the Transformer model.",
                "model_status": model_status(),
            },
        }

    pairs = []
    for actual in realtime:
        candidates = [
            item for item in predicted
            if item.forecast_for and actual.created_at and abs((item.forecast_for - actual.created_at).total_seconds()) <= 7200
        ]
        if candidates:
            pairs.append((actual, sorted(candidates, key=lambda item: abs((item.forecast_for - actual.created_at).total_seconds()))[0]))

    if not pairs:
        pairs = list(zip(realtime[:20], predicted[:20]))

    errors = []
    field_errors = {field: [] for field in WEATHER_FIELDS}
    field_offsets = {field: [] for field in WEATHER_FIELDS}
    for actual, forecast in pairs:
        for field in WEATHER_FIELDS:
            actual_value = getattr(actual, field, None)
            forecast_value = getattr(forecast, field, None)
            if actual_value is not None and forecast_value is not None:
                difference = float(actual_value) - float(forecast_value)
                errors.append(abs(difference))
                field_errors[field].append(abs(difference))
                field_offsets[field].append(difference)

    if not errors:
        return {
            "status": "insufficient_data",
            "samples_count": len(pairs),
            "accuracy_score": None,
            "mean_absolute_error": None,
            "details": {"message": "Weather records exist but do not contain comparable numeric fields."},
        }

    mae = mean(errors)
    offsets = {
        field: _round(mean(values), 3)
        for field, values in field_offsets.items()
        if values
    }
    per_field_mae = {
        field: _round(mean(values), 3)
        for field, values in field_errors.items()
        if values
    }
    accuracy = max(0.0, min(99.0, 100.0 - mae * 3.5))
    if offsets:
        _save_calibration({
            "offsets": offsets,
            "per_field_mae": per_field_mae,
            "samples_count": len(pairs),
            "accuracy_score": _round(accuracy),
            "updated_at": datetime.utcnow().isoformat(),
            "model_status": model_status(),
        })

    return {
        "status": "calibrated" if _load_model() is not None else "baseline_calibrated",
        "samples_count": len(pairs),
        "accuracy_score": _round(accuracy),
        "mean_absolute_error": _round(mae),
        "details": {
            "message": "Quarterly training run evaluated prediction error against realtime weather records.",
            "model_status": model_status(),
            "tensorflow_training_available": _load_model() is not None,
            "calibration_file": CALIBRATION_FILE,
            "offsets": offsets,
            "per_field_mae": per_field_mae,
        },
    }
