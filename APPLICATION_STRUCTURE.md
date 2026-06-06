# NuroAgro Application Structure

This document explains which file is responsible for each major NuroAgro feature.

## Main Answer: Which Model Analyzes History Data?

NuroAgro uses different models/agents for different history types:

| History/Data Type | Main File | Model/Data File | What It Does |
|---|---|---|---|
| Sensor history every 1 hour and manual farm analysis | `sensor_agent.py` | No `.pt`/`.keras`; rule-based analysis code | Analyzes temperature, humidity, soil moisture, water level, light, rain, gas, and motion history, then creates farm recommendations. |
| Weather prediction and 3-month weather analysis | `weather_agent.py` | `weather_prediction_transformer_model.keras` + `scaler.pkl` | Runs the supplied Transformer weather model, converts scaled output back to weather units, stores predicted weather, summarizes 3-month weather records, and generates crop advice. |
| 3-month weather training/calibration | `weather_agent.py` | Runtime file: `weather_calibration.json` | Created after enough realtime/predicted weather pairs exist. Stores learned correction offsets so future predictions can be adjusted. |
| Plant disease detection from manual image or ESP camera | `disease_ml.py` | `best.pt` | Runs YOLO disease detection, creates annotated image, stores diagnosis and treatment recommendation. |
| ChatGPT crop advice | `weather_agent.py` | External OpenAI API, configured by `OPENAI_API_KEY` | Uses predicted weather plus 3-month weather summary to suggest good crops for the next 3 months. If no API key is set, local crop advice is used. |

Important: `best.pt` is only for image disease detection. It does not analyze sensor or weather history.

## Backend Files

| File | Responsibility |
|---|---|
| `app_iot.py` | Main Flask application. Creates the app, configures CORS/session/database, loads YOLO, serves the built React frontend, creates local database tables, and starts routes. |
| `run_iot.py` | Clean production-style local runner for the Flask app on port `5001` with the reloader disabled. Use this for normal local running. |
| `routes/api.py` | All API endpoints: auth, admin dashboard, project setup, sensor ingestion, relay commands, disease upload/history, weather prediction/history/training, recommendations, notifications, and Supabase status. |
| `models.py` | SQLAlchemy database tables: users, projects, devices, sensor readings, relay status, disease detections, weather records, weather training runs, recommendations, notifications, logs. |
| `sensor_agent.py` | Farm condition analyzer. Reads stored sensor history and generates hourly/manual recommendations. |
| `weather_agent.py` | Weather ML service. Loads `weather_prediction_transformer_model.keras`, loads `scaler.pkl`, predicts weather, summarizes 3-month weather history, calls ChatGPT/local crop agent, and writes calibration data. |
| `disease_ml.py` | YOLO disease detection helper. Uses `best.pt`, saves annotated images, returns disease name, confidence, severity, boxes, and recommendations. |
| `supabase_bridge.py` | Mirrors local SQLite/PostgreSQL records into Supabase REST tables using `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY`. |
| `supabase_schema.sql` | Supabase table schema and policies. Run this in Supabase SQL editor before expecting remote database sync to work. |

## Frontend Files

| File | Responsibility |
|---|---|
| `frontend_jsx/src/App.jsx` | Main React application. Contains login/register, project setup, dashboard, weather panel, disease page, admin page, sensor cards, relay controls, recommendations, notifications, and API calls. |
| `frontend_jsx/src/styles.css` | Full UI styling for NuroAgro. |
| `frontend_jsx/dist/` | Built frontend served by Flask. Created by `npm run build`. |
| `frontend_jsx/package.json` | Vite/React scripts and frontend dependencies. |

## ML And Data Files

| File | Used By | Purpose |
|---|---|---|
| `best.pt` | `disease_ml.py` | YOLO plant disease detection model. |
| `weather_prediction_transformer_model.keras` | `weather_agent.py` | Transformer weather prediction model. |
| `scaler.pkl` | `weather_agent.py` | MinMaxScaler used to scale sensor/weather input and inverse-transform model output. |
| `weather_calibration.json` | `weather_agent.py` | Runtime calibration offsets created by 3-month training. This file is ignored by git. |

## Firmware Files

| File | Board | Purpose |
|---|---|---|
| `esp32_firmware/main.ino` | ESP32-WROOM-32 | Reads main sensors, sends `/api/sensor-data`, polls `/api/device-command/<device_id>`, controls relays. |
| `esp32_firmware/camera_ov6767_upload.ino` | Camera-capable ESP32 board | Captures plant images and uploads them to `/api/upload-disease-image` for YOLO disease detection. |

## Application Workflow

1. User registers from the React app.
2. Admin opens `/admin`, logs in with the admin password, and accepts or rejects the user.
3. Accepted user logs in and creates a project with area in square feet, location, farming mode, floors, and water system.
4. ESP32-WROOM sends sensor packets to `POST /api/sensor-data`.
5. Backend stores sensor data locally and mirrors it to Supabase.
6. Backend checks moisture, water level, rain, gas, light, and motion thresholds and creates notifications.
7. Every hour, the app can analyze recent sensor history using `sensor_agent.py`.
8. Every 30 minutes, the weather predictor uses `weather_agent.py` to save predicted weather and notify the user.
9. The ChatGPT crop agent uses weather prediction plus 3-month history to suggest plants for the next 3 months.
10. User can press "Train 3-Month Model"; backend evaluates predicted vs realtime weather history and stores a training/calibration run.
11. Disease detection works two ways:
    - Manual upload from the app calls `POST /api/disease-detection`.
    - ESP camera uploads images to `POST /api/upload-disease-image`.
12. Admin dashboard shows users, accepted/pending/rejected counts, visitors, devices, sensor records, disease scans, weather records, and recommendations.

## Important Environment Variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Local backend database. Default is SQLite. |
| `SUPABASE_URL` | Supabase project URL for backend mirroring. |
| `SUPABASE_PUBLISHABLE_KEY` | Supabase key for backend bridge. |
| `SUPABASE_SYNC_ENABLED` | Set `true` to enable Supabase mirroring. |
| `DEVICE_API_KEY` | ESP32 API key sent as `X-API-Key`. |
| `ADMIN_PASSWORD` | Admin dashboard password. |
| `WEATHER_MODEL_PATH` | Path to `.keras` weather model. |
| `WEATHER_SCALER_PATH` | Path to scaler `.pkl`. |
| `WEATHER_CALIBRATION_PATH` | Path for runtime calibration JSON. |
| `OPENAI_API_KEY` | Enables ChatGPT crop advice. |
| `OPENAI_MODEL` | OpenAI model name for crop advice. |

