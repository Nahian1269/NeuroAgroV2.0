# NuroAgro ESP32 Hardware Pin Diagram

This hardware plan is for the current NuroAgro application:

- Main controller: ESP32-WROOM-32 running `esp32_firmware/main.ino`
- Camera controller: separate camera-capable ESP32 board running `esp32_firmware/camera_ov6767_upload.ino`
- Backend server: Flask app on `http://<server-ip>:5001`
- Required API key: same value as backend `DEVICE_API_KEY`, sent as `X-API-Key`

Use two ESP32 boards. A camera module consumes many pins and should not be wired to the same ESP32-WROOM that reads sensors and drives relays.

## Why An ADC Expander Is Recommended

The full NuroAgro sensor list has many analog outputs:

- Soil moisture
- MQ-2 / MQ-5 / MQ-7 / MQ-135 gas sensors
- TEMT6000 light sensor
- Raindrop sensor
- Water level sensor

ESP32-WROOM has limited reliable ADC pins when WiFi is active. ADC2 pins conflict with WiFi. For a professional build, use ESP32 ADC1 pins for critical sensors and use an ADS1115 I2C ADC module for extra analog sensors.

## Main ESP32-WROOM Pin Map

Recommended full build map:

| Module | Signal | ESP32 Pin | Voltage/Interface | Notes |
|---|---|---:|---|---|
| DHT11 or DHT7 | DATA | GPIO 4 | Digital, 3.3V | Add 10k pull-up from DATA to 3.3V. |
| Soil moisture | AO | GPIO 34 | ADC1 input | Input-only pin. Use 3.3V-safe analog output. |
| MQ-5 | AO | GPIO 35 | ADC1 input | LPG/natural gas. Use voltage divider if AO can reach 5V. |
| MQ-7 | AO | GPIO 32 | ADC1 input | Carbon monoxide. Needs warm-up/calibration. |
| MQ-135 | AO | GPIO 33 | ADC1 input | Air quality. Needs warm-up/calibration. |
| TEMT6000 light | SIG | GPIO 36 | ADC1 input | Lux approximation; calibrate in firmware. |
| Raindrop sensor | AO | GPIO 39 | ADC1 input | Input-only pin. |
| PIR motion sensor | OUT | GPIO 23 | Digital input | Use 3.3V output or level shifting. |
| Pump A relay | IN1 | GPIO 12 | Digital output | Pump A/manual/auto watering. |
| Pump B relay | IN2 | GPIO 14 | Digital output | Second water pump or nutrient pump. |
| Blue UV light relay | IN3 | GPIO 13 | Digital output | UV/grow light on/off. |
| UV dim/PWM driver | PWM | GPIO 15 | PWM output | Use only with MOSFET/LED driver, not a relay. |
| ADS1115 SDA | SDA | GPIO 21 | I2C | For extra analog sensors. |
| ADS1115 SCL | SCL | GPIO 22 | I2C | For extra analog sensors. |

## ADS1115 Extra Analog Map

Use ADS1115 at address `0x48`.

| Module | ADS1115 Channel | Notes |
|---|---:|---|
| Water level sensor | A0 | Store as `water_level` percent. |
| MQ-2 | A1 | Smoke/LPG. |
| Optional sound sensor | A2 | Backend supports `sound`; optional hardware. |
| Spare analog input | A3 | Use for EC/pH/TDS expansion later. |

If you do not use ADS1115, reduce the sensor list or move some sensors to a second ESP32. Avoid ESP32 ADC2 analog reads while WiFi is active.

## Firmware Status

`esp32_firmware/main.ino` has been updated for the production map above:

- Pump A relay on GPIO 12
- Pump B relay on GPIO 14
- Blue UV/grow light relay on GPIO 13
- UV PWM level on GPIO 15
- Rain sensor on GPIO 39
- Motion sensor on GPIO 23
- TEMT6000 light sensor on GPIO 36
- ADS1115 water-level, MQ-2, and optional sound sensor channels
- JSON fields: `rain_level`, `water_level`, `motion_detected`, `pump_b_status`, `uv_light_level`

The backend accepts these fields in `POST /api/sensor-data` and returns relay states from `GET /api/device-command/<device_id>`.

## Relay Wiring

Use a relay module with optocoupler/transistor input. Do not drive a bare relay coil directly from ESP32 GPIO.

### Pump A

```text
Pump supply positive -> relay COM
relay NO -> pump A positive
pump A negative -> pump supply negative
ESP32 GPIO12 -> relay IN1
relay VCC -> relay supply
relay GND -> common GND
```

### Pump B

```text
Pump supply positive -> relay COM
relay NO -> pump B positive
pump B negative -> pump supply negative
ESP32 GPIO14 -> relay IN2
relay VCC -> relay supply
relay GND -> common GND
```

### Blue UV/Grow Light

```text
Light supply positive -> relay COM
relay NO -> UV light positive
UV light negative -> light supply negative
ESP32 GPIO13 -> relay IN3
```

For brightness/lux adjustment, use a MOSFET or dimmable LED driver:

```text
ESP32 GPIO15 PWM -> MOSFET/LED driver PWM input
LED driver output -> UV light
driver GND -> common GND
```

A relay can switch UV lights on/off only. A relay cannot dim lux.

## Power Plan

| Rail | Use | Notes |
|---|---|---|
| ESP32 USB or 5V buck | ESP32 board | Use stable 5V input or USB. |
| 3.3V | DHT pull-up, low-power 3.3V logic sensors | Do not power MQ sensors from ESP32 3.3V. |
| 5V external | MQ sensors, ADS1115, relay module if 5V relay board | Common GND required unless fully opto-isolated. |
| 6V external | 6V relay board if your relay module is 6V | Match relay coil voltage to relay module rating. |
| Pump supply | Water pumps | Usually separate 5V/6V/12V depending on pump. |
| Light supply | UV/grow lights | Use correct current-rated supply and driver. |

Important safety:

- ESP32 GPIO and ADC pins are not 5V tolerant.
- Add a voltage divider or level shifter for any 5V analog/digital output.
- Use flyback protection for motors/relay coils if your module does not include it.
- Keep pump and light current off the breadboard.
- Use fuses or current-limited supplies for pumps and lights.
- Connect grounds together for ESP32, sensors, relay module, pump supply, and light driver unless using isolated relay inputs.

## ESP Camera Board Pin Map

Use a separate camera-capable ESP32 board for `esp32_firmware/camera_ov6767_upload.ino`.

Default camera firmware map:

| Camera Signal | ESP32 Pin |
|---|---:|
| XCLK | GPIO 21 |
| SIOD / SDA | GPIO 26 |
| SIOC / SCL | GPIO 27 |
| VSYNC | GPIO 25 |
| HREF | GPIO 23 |
| PCLK | GPIO 22 |
| D7 / Y9 | GPIO 19 |
| D6 / Y8 | GPIO 18 |
| D5 / Y7 | GPIO 5 |
| D4 / Y6 | GPIO 4 |
| D3 / Y5 | GPIO 15 |
| D2 / Y4 | GPIO 14 |
| D1 / Y3 | GPIO 13 |
| D0 / Y2 | GPIO 12 |
| Manual capture button | GPIO 0 |
| Camera 3.3V | 3.3V |
| Camera GND | GND |

OV6767 breakouts vary. Confirm the exact breakout pin labels before powering the module.

## Backend Payload Fields

The ESP32 main controller sends sensor data to:

```text
POST http://<server-ip>:5001/api/sensor-data
Header: X-API-Key: <DEVICE_API_KEY>
```

Recommended JSON fields:

```json
{
  "device_id": "ESP32_001",
  "temperature": 24.6,
  "humidity": 63.5,
  "soil_moisture": 48,
  "mq2": 120,
  "mq5": 145,
  "mq7": 90,
  "mq135": 210,
  "light": 850,
  "rain_level": 12,
  "water_level": 76,
  "motion_detected": false,
  "pump_status": false,
  "pump_b_status": false,
  "light_status": true,
  "pressure": 1014.31,
  "rainfall": 25.64
}
```

The ESP32 polls relay commands from:

```text
GET http://<server-ip>:5001/api/device-command/ESP32_001
Header: X-API-Key: <DEVICE_API_KEY>
```

Commands supported by the backend include:

- `pump_on`
- `pump_off`
- `pump_b_on`
- `pump_b_off`
- `light_on`
- `light_off`
- `uv_level`
- `camera_scan`
- `capture_disease_image`

## Camera Upload Endpoint

The ESP camera uploads plant images to:

```text
POST http://<server-ip>:5001/api/upload-disease-image
Header: X-API-Key: <DEVICE_API_KEY>
Form fields:
  device_id = ESP32_001
  image = leaf.jpg
```

The backend stores the image, runs `best.pt` through `disease_ml.py`, creates a disease record, mirrors to Supabase, and shows the result in the Disease page.

## Build Order

1. Start backend with `run_iot.py` and confirm `http://127.0.0.1:5001/admin` opens.
2. Run `supabase_schema.sql` in Supabase SQL editor.
3. Create/accept a user from `/admin`.
4. Register the ESP32 device ID, for example `ESP32_001`.
5. Wire only ESP32, DHT, and one relay first.
6. Upload `esp32_firmware/main.ino` and confirm serial output.
7. Add analog sensors one by one.
8. Add relay loads without pumps/lights first and verify relay clicks from the Dashboard.
9. Connect pumps and UV lights only after relay logic is correct.
10. Add the camera ESP32 and upload `esp32_firmware/camera_ov6767_upload.ino`.
11. Test manual image upload from the app.
12. Test ESP camera upload and confirm disease history appears.

## Calibration Notes

- MQ gas sensors need warm-up time and calibration.
- Soil moisture raw dry/wet values differ by probe. Calibrate dry and wet values in firmware.
- TEMT6000 lux conversion is approximate unless calibrated with a lux meter.
- Raindrop sensors report wetness level, not exact rainfall. The backend can store true `rainfall` in mm if firmware sends that field.
- Water level sensor output must be converted to percent before sending or converted in firmware.
