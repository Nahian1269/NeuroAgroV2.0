# NuroAgro Smart Farming + YOLO Disease Detection

NuroAgro is an IoT farming web app for vertical, hydroponic, aquaponic, hybrid, and traditional farms. It is built on Flask, SQLite/Supabase mirroring, ESP32-WROOM sensor firmware, React/Vite, and YOLO leaf disease detection.

## Main Features

- User registration, admin acceptance, login, and user deletion
- Project setup with land size, location, weather profile, vertical floors, water system, plant suggestions, fish suggestions, and farming-mode suitability
- ESP32 dashboard for DHT11, soil moisture, MQ-05, MQ-07, MQ-135, TEMT6000 lux, raindrop, water level, motion, pump, relay, and UV light state
- Manual relay control for two water pumps and blue UV grow lights
- Automatic watering when soil moisture is low and the reservoir has water
- Notifications for dry soil, saturated soil, rain, low water level, motion, high temperature, poor air quality, and disease detections
- Leaf disease detection from manual upload or ESP camera upload
- OV6767 still-image upload firmware template
- Virtual Farm Mode for local demos and product previews without ESP32 hardware
- In-app Manual page with setup, wiring, local run, and Render deployment guidance
- Geolocation daily weather sync saved to the database for 3-month prediction calibration
- CropGuard Risk Index combining sensors, disease scans, predicted weather, and daily geo weather

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd frontend_jsx
npm install
npm run build
cd ..
python run_iot.py
```

Open `http://127.0.0.1:5001`.

Flask serves the built React application from `frontend_jsx/dist` and exposes the API from the same backend server.

You can also use the project helper:

```powershell
npm install
npm --prefix frontend_jsx install
npm start
```

If the browser does not open automatically, open the URL printed in the terminal.

Demo account:

```text
username: demo
password: demo123
```

## Important Files

| File | Purpose |
|---|---|
| `app_iot.py` | Main Flask IoT application |
| `models.py` | Database models |
| `routes/api.py` | ESP32 and app API routes |
| `frontend_jsx/` | Single React frontend |
| `esp32_firmware/main.ino` | ESP32-WROOM sensor and relay firmware |
| `esp32_firmware/camera_ov6767_upload.ino` | ESP32 camera still-image uploader |
| `PIN_DIAGRAM.md` | Wiring and pin map |

For wiring and hardware assembly, start with `PIN_DIAGRAM.md`.

## Render Deployment

This repository includes `render.yaml` for a Render Python web service.

Render build command:

```bash
pip install -r requirements.txt && npm --prefix frontend_jsx ci && npm --prefix frontend_jsx run build
```

Render start command:

```bash
gunicorn "app_iot:create_app()" --bind 0.0.0.0:$PORT --workers 1 --timeout 180
```

Before deploying to GitHub/Render:

```powershell
git status
git add .
git commit -m "Prepare NuroAgro for Render deployment"
git push
```

In Render, create a Blueprint from this repo or create a Python Web Service manually using the commands above. Set `DEVICE_API_KEY` and `ADMIN_PASSWORD` in Render, then use the same `DEVICE_API_KEY` in `esp32_firmware/main.ino`.

Production defaults keep the app ready for product demos:

- `WEATHER_MODEL_ENABLED=true` attempts the Transformer weather model when `weather_prediction_transformer_model.keras` and `scaler.pkl` are available.
- `WEATHER_TRANSFORMER_TIMEOUT_SECONDS=12` records fallback status if the Transformer path is too slow or unavailable.
- `WEATHER_GEO_AUTOSYNC=true` saves Open-Meteo current and daily weather by project/user coordinates.
- `GEO_WEATHER_TIMEOUT_SECONDS=8` keeps geolocation weather sync from blocking the app too long.
- `DISEASE_MODEL_PRELOAD=true` warms YOLO after startup so the first scan is smoother.
- `DISEASE_MAX_ANALYSIS_EDGE=960` and `DISEASE_YOLO_IMGSZ=512` keep disease scans responsive.
- `DISEASE_INFERENCE_SUBPROCESS=true` isolates YOLO/PyTorch from Flask so a bad scan cannot crash the web app.
- `DISEASE_INFERENCE_TIMEOUT_SECONDS=110` returns a clean UI error if a scan stalls too long.
- `DISEASE_CONFIDENCE_THRESHOLD=0.20` matches the supplied `best.pt` model, whose valid disease boxes often score around 20-40%.
- `DISEASE_POSSIBLE_CONFIDENCE_THRESHOLD=0.12` keeps very weak disease evidence visible as "possible" instead of silently reporting healthy.

Render is preferred for the full product because it can run Flask, React build output, SQLite/Postgres, TensorFlow, and YOLO together. Vercel is suitable for a separate frontend-only deployment, but the Python API and ML models should remain on Render or another Python web service. Use a paid Render plan for smoother ML cold starts.

The deployed app includes project setup, user/admin approval, ESP32 sensor dashboard, relay controls, weather prediction and calibration, disease detection, recommendations, history, profile, chat, community posts, Supabase mirroring, and ESP camera upload support.

## Run Without IoT Hardware

After login, open Dashboard and press **Virtual Farm**. The app creates a realistic sensor packet through `/api/demo/seed/<device_id>`, saves it in the database, generates realtime weather, and refreshes the same dashboard used by ESP32 hardware. This lets you present the product locally or on Render before wiring the physical farm.

## ESP32 Connection

For your hardware list, use the first diagram in `PIN_DIAGRAM.md`:

- ESP32-WROOM-32
- MQ7, MQ135, MQ5
- DHT11
- Raindrop sensor
- Soil moisture sensor
- Relay module
- PIR sensor

Upload `esp32_firmware/main.ino`, keep `USE_ADS1115` set to `0`, and update `SSID`, `PASSWORD`, `SERVER_URL`, `DEVICE_ID`, and `API_KEY`.
