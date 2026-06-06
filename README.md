# NuroAgro Smart Farming + YOLO Disease Detection

NuroAgro is an IoT farming web app for vertical, hydroponic, aquaponic, hybrid, and traditional farms. It is built on Flask, SQLite/Supabase mirroring, ESP32-WROOM sensor firmware, React/Vite, and YOLO leaf disease detection.

## Main Features

- User registration, admin acceptance, login, and user deletion
- Project setup with land size, location, weather profile, vertical floors, water system, plant suggestions, fish suggestions, and farming-mode suitability
- ESP32 dashboard for DHT11/DHT7, soil moisture, MQ-05, MQ-07, MQ-135, TEMT6000 lux, raindrop, water level, motion, pump, relay, and UV light state
- Manual relay control for two water pumps and blue UV grow lights
- Automatic watering when soil moisture is low and the reservoir has water
- Notifications for dry soil, saturated soil, rain, low water level, motion, high temperature, poor air quality, and disease detections
- Leaf disease detection from manual upload or ESP camera upload
- OV6767 still-image upload firmware template

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd frontend_jsx
npm install
npm run build
cd ..
python app_iot.py
```

Open `http://127.0.0.1:5001`.

Flask serves the built React application from `frontend_jsx/dist` and exposes the API from the same backend server.

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
