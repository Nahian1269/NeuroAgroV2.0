/*
 * IoT Vertical Farming System - ESP32 Main Firmware
 * 
 * This code handles:
 * - Sensor data collection from multiple environmental sensors
 * - Motor/Pump control via relays
 * - WiFi connectivity and MQTT/HTTP communication
 * - Real-time data transmission to Flask backend
 * - Remote device control
 * 
 * Hardware: ESP32-WROOM-32
 * Sensors: DHT11/DHT7, Soil Moisture, MQ-2/5/7/135, TEMT6000,
 *          Raindrop, Water Level, PIR Motion, optional Sound
 * Actuators: 2x pumps, relay UV/grow light power, PWM UV dimming
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <Wire.h>
#include <Adafruit_ADS1X15.h>
#include <time.h>

// ==================== CONFIGURATION ====================

// WiFi Configuration
const char* SSID = "YOUR_SSID";                    // Change to your WiFi name
const char* PASSWORD = "YOUR_PASSWORD";             // Change to your WiFi password
const char* SERVER_URL = "http://192.168.x.x:5001"; // Change to your server IP:port
const char* DEVICE_ID = "ESP32_001";
const char* API_KEY = "farm-device-key";            // Must be sent as X-API-Key

// Server Endpoints
const char* SENSOR_DATA_ENDPOINT = "/api/sensor-data";
const char* COMMAND_CHECK_ENDPOINT = "/api/device-command/";

// Data transmission interval (milliseconds)
#define SENSOR_READ_INTERVAL 10000  // Read sensors every 10 seconds
#define DATA_SEND_INTERVAL 60000    // Send data every 60 seconds
#define USE_ADS1115 true            // Required for the full NuroAgro analog sensor set

// ==================== PIN DEFINITIONS ====================

// Sensor Pins
#define DHT_PIN 4             // GPIO 4 - DHT11/DHT7 data
#define SOIL_MOISTURE_PIN 34  // GPIO 34 - ADC1 input
#define MQ5_PIN 35            // GPIO 35 - ADC1 input - LPG/Natural Gas
#define MQ7_PIN 32            // GPIO 32 - ADC1 input - Carbon Monoxide
#define MQ135_PIN 33          // GPIO 33 - ADC1 input - Air Quality
#define LIGHT_PIN 36          // GPIO 36 - ADC1 input - TEMT6000 lux sensor
#define RAIN_PIN 39           // GPIO 39 - ADC1 input - Raindrop sensor
#define MOTION_PIN 23         // GPIO 23 - Digital input - PIR/motion

// Actuator Pins
#define PUMP_RELAY_PIN 12     // GPIO 12 - Relay 1 for pump A
#define PUMP_B_RELAY_PIN 14   // GPIO 14 - Relay 2 for pump B/nutrient pump
#define LIGHT_RELAY_PIN 13    // GPIO 13 - Relay 3 for blue UV/grow light power
#define UV_PWM_PIN 15         // GPIO 15 - PWM for dimmable UV LED driver

// ADS1115 channels
#define ADS_WATER_LEVEL_CHANNEL 0
#define ADS_MQ2_CHANNEL 1
#define ADS_SOUND_CHANNEL 2

// DHT11 Type
#define DHT_TYPE DHT11

// ==================== GLOBAL OBJECTS ====================

DHT dht(DHT_PIN, DHT_TYPE);
HTTPClient http;
Adafruit_ADS1115 ads;
bool ads_ready = false;

// Data structures
struct SensorData {
  float temperature;
  float humidity;
  int soil_moisture;
  int mq2_reading;
  int mq5_reading;
  int mq7_reading;
  int mq135_reading;
  int sound_level;
  int light_intensity;
  int rain_level;
  int water_level;
  bool motion_detected;
  unsigned long timestamp;
};

struct DeviceStatus {
  bool pump_on;
  bool pump_b_on;
  bool light_on;
  int uv_light_level;
  bool auto_watering_enabled;
  int moisture_threshold;
  unsigned long last_watering;
  unsigned long scheduled_watering;
};

SensorData current_sensor_data;
DeviceStatus device_status = {false, false, false, 65, true, 30, 0, 0};

// Timing variables
unsigned long last_sensor_read = 0;
unsigned long last_data_send = 0;
bool wifi_connected = false;
String last_processed_command_time = "";

// ==================== SETUP FUNCTION ====================

void setup() {
  // Initialize Serial
  Serial.begin(115200);
  delay(100);
  
  Serial.println("\n\n================================");
  Serial.println("ESP32 Vertical Farming System");
  Serial.println("================================\n");
  
  // Initialize pin modes
  pinMode(PUMP_RELAY_PIN, OUTPUT);
  pinMode(PUMP_B_RELAY_PIN, OUTPUT);
  pinMode(LIGHT_RELAY_PIN, OUTPUT);
  pinMode(UV_PWM_PIN, OUTPUT);
  pinMode(MOTION_PIN, INPUT);
  
  // Set relays to OFF initially
  digitalWrite(PUMP_RELAY_PIN, LOW);
  digitalWrite(PUMP_B_RELAY_PIN, LOW);
  digitalWrite(LIGHT_RELAY_PIN, LOW);
  analogWrite(UV_PWM_PIN, 0);
  
  Serial.println("[INIT] GPIO pins initialized");
  
  // Initialize DHT sensor
  dht.begin();
  Serial.println("[INIT] DHT11 sensor initialized");

  // Initialize ADS1115 for extra analog sensors
  if (USE_ADS1115) {
    Wire.begin(21, 22);
    ads_ready = ads.begin(0x48);
    if (ads_ready) {
      ads.setGain(GAIN_ONE); // +/-4.096V range, good for 3.3V sensor outputs
      Serial.println("[INIT] ADS1115 initialized at 0x48");
    } else {
      Serial.println("[WARN] ADS1115 not found. Water level, MQ-2, and sound will read 0.");
    }
  }
  
  // Connect to WiFi
  connectToWiFi();
  
  Serial.println("[INIT] System ready!\n");
}

// ==================== MAIN LOOP ====================

void loop() {
  unsigned long current_millis = millis();
  
  // Check WiFi connection periodically
  if (!wifi_connected || WiFi.status() != WL_CONNECTED) {
    if (current_millis % 30000 == 0) {  // Check every 30 seconds
      connectToWiFi();
    }
  }
  
  // Read sensors at specified interval
  if (current_millis - last_sensor_read >= SENSOR_READ_INTERVAL) {
    readAllSensors();
    last_sensor_read = current_millis;
  }
  
  // Send data to server at specified interval
  if (current_millis - last_data_send >= DATA_SEND_INTERVAL && wifi_connected) {
    sendSensorDataToServer();
    checkForRemoteCommands();
    last_data_send = current_millis;
  }
  
  delay(100);  // Small delay to prevent watchdog reset
}

// ==================== WiFi FUNCTIONS ====================

void connectToWiFi() {
  if (wifi_connected && WiFi.status() == WL_CONNECTED) {
    return;
  }
  
  Serial.print("[WiFi] Connecting to: ");
  Serial.println(SSID);
  
  WiFi.mode(WIFI_STA);
  WiFi.begin(SSID, PASSWORD);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    wifi_connected = true;
    Serial.println("\n[WiFi] Connected!");
    Serial.print("[WiFi] IP Address: ");
    Serial.println(WiFi.localIP());
  } else {
    wifi_connected = false;
    Serial.println("\n[WiFi] Connection failed!");
  }
}

// ==================== SENSOR READING FUNCTIONS ====================

void readAllSensors() {
  Serial.println("\n[SENSORS] Reading all sensors...");
  
  // Read DHT11
  readDHT11();
  
  // Read analog sensors
  readSoilMoisture();
  readMQSensors();
  readSoundSensor();
  readLightSensor();
  readRainSensor();
  readWaterLevelSensor();
  readMotionSensor();
  
  // Log current readings
  logSensorData();
}

void readDHT11() {
  // DHT11 readings can fail, retry if necessary
  float temp = dht.readTemperature();
  float humid = dht.readHumidity();
  
  if (isnan(temp) || isnan(humid)) {
    Serial.println("[DHT11] Read failed! Using last values.");
    return;
  }
  
  current_sensor_data.temperature = temp;
  current_sensor_data.humidity = humid;
  
  Serial.print("[DHT11] Temp: ");
  Serial.print(temp);
  Serial.print("°C, Humidity: ");
  Serial.print(humid);
  Serial.println("%");
}

void readSoilMoisture() {
  int raw_value = analogRead(SOIL_MOISTURE_PIN);
  // Convert to percentage: dry soil (~4095) to wet soil (~1000)
  int moisture = map(raw_value, 4095, 1000, 0, 100);
  moisture = constrain(moisture, 0, 100);
  
  current_sensor_data.soil_moisture = moisture;
  
  Serial.print("[MOISTURE] Value: ");
  Serial.print(raw_value);
  Serial.print(" | Moisture: ");
  Serial.print(moisture);
  Serial.println("%");
  
  // Auto-trigger pump if soil moisture is too low
  if (device_status.auto_watering_enabled && moisture < device_status.moisture_threshold && !device_status.pump_on) {
    Serial.println("[AUTO] Low moisture detected! Turning pump ON.");
    setPumpStatus(true);
  } else if (device_status.auto_watering_enabled && moisture > 70 && device_status.pump_on) {
    Serial.println("[AUTO] Moisture sufficient. Turning pump OFF.");
    setPumpStatus(false);
  }
}

void readMQSensors() {
  // MQ sensors need to be read with a high sampling rate
  // Taking average of 10 readings for stability
  
  int mq2_sum = 0, mq5_sum = 0, mq7_sum = 0, mq135_sum = 0;
  const int samples = 10;
  
  for (int i = 0; i < samples; i++) {
    mq2_sum += readADSRaw(ADS_MQ2_CHANNEL);
    mq5_sum += analogRead(MQ5_PIN);
    mq7_sum += analogRead(MQ7_PIN);
    mq135_sum += analogRead(MQ135_PIN);
    delay(10);
  }
  
  current_sensor_data.mq2_reading = mq2_sum / samples;
  current_sensor_data.mq5_reading = mq5_sum / samples;
  current_sensor_data.mq7_reading = mq7_sum / samples;
  current_sensor_data.mq135_reading = mq135_sum / samples;
  
  Serial.print("[MQ-2] LPG/Smoke: ");
  Serial.print(current_sensor_data.mq2_reading);
  Serial.print(" | [MQ-5] LPG/Gas: ");
  Serial.print(current_sensor_data.mq5_reading);
  Serial.print(" | [MQ-7] CO: ");
  Serial.print(current_sensor_data.mq7_reading);
  Serial.print(" | [MQ-135] Air Quality: ");
  Serial.println(current_sensor_data.mq135_reading);
}

void readSoundSensor() {
  // Sound sensor readings (multiple samples for stability)
  int sound_sum = 0;
  const int samples = 5;
  
  for (int i = 0; i < samples; i++) {
    sound_sum += readADSRaw(ADS_SOUND_CHANNEL);
    delay(5);
  }
  
  current_sensor_data.sound_level = sound_sum / samples;
  
  Serial.print("[SOUND] Level: ");
  Serial.println(current_sensor_data.sound_level);
}

void readLightSensor() {
  int raw_light = analogRead(LIGHT_PIN);
  // Convert ADC reading (0-4095) to lux approximation (0-2000).
  // Calibrate against a real lux meter for production.
  int light_intensity = map(raw_light, 0, 4095, 0, 2000);
  
  current_sensor_data.light_intensity = light_intensity;
  
  Serial.print("[LIGHT] Raw: ");
  Serial.print(raw_light);
  Serial.print(" | Intensity: ");
  Serial.print(light_intensity);
  Serial.println(" lux (approx)");
}

void readRainSensor() {
  int raw_rain = analogRead(RAIN_PIN);
  // Most raindrop modules output high when dry and lower when wet.
  int rain_level = map(raw_rain, 4095, 1200, 0, 100);
  rain_level = constrain(rain_level, 0, 100);

  current_sensor_data.rain_level = rain_level;

  Serial.print("[RAIN] Raw: ");
  Serial.print(raw_rain);
  Serial.print(" | Wetness: ");
  Serial.print(rain_level);
  Serial.println("%");
}

void readWaterLevelSensor() {
  int raw_water = readADSRaw(ADS_WATER_LEVEL_CHANNEL);
  int water_level = map(raw_water, 500, 16000, 0, 100);
  water_level = constrain(water_level, 0, 100);

  current_sensor_data.water_level = water_level;

  Serial.print("[WATER] Raw: ");
  Serial.print(raw_water);
  Serial.print(" | Level: ");
  Serial.print(water_level);
  Serial.println("%");
}

void readMotionSensor() {
  current_sensor_data.motion_detected = digitalRead(MOTION_PIN) == HIGH;
  Serial.print("[MOTION] ");
  Serial.println(current_sensor_data.motion_detected ? "Detected" : "Clear");
}

int readADSRaw(uint8_t channel) {
  if (!ads_ready) {
    return 0;
  }
  int16_t raw = ads.readADC_SingleEnded(channel);
  return max(0, (int)raw);
}

void logSensorData() {
  Serial.println("\n[DATA SUMMARY]");
  Serial.print("  Temperature: ");
  Serial.print(current_sensor_data.temperature);
  Serial.println(" °C");
  Serial.print("  Humidity: ");
  Serial.print(current_sensor_data.humidity);
  Serial.println(" %");
  Serial.print("  Soil Moisture: ");
  Serial.print(current_sensor_data.soil_moisture);
  Serial.println(" %");
  Serial.print("  MQ-2: ");
  Serial.println(current_sensor_data.mq2_reading);
  Serial.print("  Sound: ");
  Serial.println(current_sensor_data.sound_level);
  Serial.print("  Light: ");
  Serial.println(current_sensor_data.light_intensity);
  Serial.print("  MQ-5: ");
  Serial.println(current_sensor_data.mq5_reading);
  Serial.print("  MQ-7: ");
  Serial.println(current_sensor_data.mq7_reading);
  Serial.print("  MQ-135: ");
  Serial.println(current_sensor_data.mq135_reading);
  Serial.print("  Rain Level: ");
  Serial.println(current_sensor_data.rain_level);
  Serial.print("  Water Level: ");
  Serial.println(current_sensor_data.water_level);
  Serial.print("  Motion: ");
  Serial.println(current_sensor_data.motion_detected ? "Detected" : "Clear");
  Serial.println("");
}

// ==================== CONTROL FUNCTIONS ====================

void setPumpStatus(bool status) {
  if (status) {
    digitalWrite(PUMP_RELAY_PIN, HIGH);
    device_status.pump_on = true;
    device_status.last_watering = millis();
    Serial.println("[CONTROL] Pump turned ON");
  } else {
    digitalWrite(PUMP_RELAY_PIN, LOW);
    device_status.pump_on = false;
    Serial.println("[CONTROL] Pump turned OFF");
  }
}

void setPumpBStatus(bool status) {
  if (status) {
    digitalWrite(PUMP_B_RELAY_PIN, HIGH);
    device_status.pump_b_on = true;
    Serial.println("[CONTROL] Pump B turned ON");
  } else {
    digitalWrite(PUMP_B_RELAY_PIN, LOW);
    device_status.pump_b_on = false;
    Serial.println("[CONTROL] Pump B turned OFF");
  }
}

void setLightStatus(bool status) {
  if (status) {
    digitalWrite(LIGHT_RELAY_PIN, HIGH);
    device_status.light_on = true;
    Serial.println("[CONTROL] Light turned ON");
  } else {
    digitalWrite(LIGHT_RELAY_PIN, LOW);
    device_status.light_on = false;
    Serial.println("[CONTROL] Light turned OFF");
  }
}

void setUVLightLevel(int level) {
  level = constrain(level, 0, 100);
  device_status.uv_light_level = level;
  int pwm_value = map(level, 0, 100, 0, 255);
  analogWrite(UV_PWM_PIN, pwm_value);
  Serial.print("[CONTROL] UV PWM level: ");
  Serial.print(level);
  Serial.println("%");
}

// ==================== COMMUNICATION FUNCTIONS ====================

void sendSensorDataToServer() {
  if (!wifi_connected) {
    Serial.println("[SERVER] WiFi not connected, skipping send.");
    return;
  }
  
  Serial.println("[SERVER] Sending sensor data...");
  
  // Create JSON document
  StaticJsonDocument<768> doc;
  doc["device_id"] = DEVICE_ID;
  doc["timestamp"] = millis() / 1000;  // Seconds since boot (should use NTP in production)
  doc["temperature"] = current_sensor_data.temperature;
  doc["humidity"] = current_sensor_data.humidity;
  doc["soil_moisture"] = current_sensor_data.soil_moisture;
  doc["mq2"] = current_sensor_data.mq2_reading;
  doc["mq5"] = current_sensor_data.mq5_reading;
  doc["mq7"] = current_sensor_data.mq7_reading;
  doc["mq135"] = current_sensor_data.mq135_reading;
  doc["sound"] = current_sensor_data.sound_level;
  doc["light"] = current_sensor_data.light_intensity;
  doc["rain_level"] = current_sensor_data.rain_level;
  doc["water_level"] = current_sensor_data.water_level;
  doc["motion_detected"] = current_sensor_data.motion_detected;
  doc["pump_status"] = device_status.pump_on;
  doc["pump_b_status"] = device_status.pump_b_on;
  doc["light_status"] = device_status.light_on;
  doc["uv_light_level"] = device_status.uv_light_level;
  
  // Serialize to string
  String json_payload;
  serializeJson(doc, json_payload);
  
  Serial.print("[SERVER] Payload: ");
  Serial.println(json_payload);
  
  // Send HTTP POST request
  http.begin(String(SERVER_URL) + String(SENSOR_DATA_ENDPOINT));
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", API_KEY);
  
  int httpCode = http.POST(json_payload);
  
  if (httpCode > 0) {
    Serial.print("[SERVER] HTTP Response Code: ");
    Serial.println(httpCode);
    
    if (httpCode == HTTP_CODE_OK || httpCode == HTTP_CODE_CREATED) {
      Serial.println("[SERVER] Data sent successfully!");
      String response = http.getString();
      Serial.print("[SERVER] Response: ");
      Serial.println(response);
    }
  } else {
    Serial.print("[SERVER] Error on HTTP request: ");
    Serial.println(http.errorToString(httpCode).c_str());
  }
  
  http.end();
}

void checkForRemoteCommands() {
  if (!wifi_connected) {
    return;
  }
  
  Serial.println("[COMMAND] Checking for remote commands...");
  
  http.begin(String(SERVER_URL) + String(COMMAND_CHECK_ENDPOINT) + String(DEVICE_ID));
  http.addHeader("X-API-Key", API_KEY);
  
  int httpCode = http.GET();
  
  if (httpCode > 0 && httpCode == HTTP_CODE_OK) {
    String response = http.getString();
    Serial.print("[COMMAND] Response: ");
    Serial.println(response);
    
    // Parse response
    StaticJsonDocument<384> response_doc;
    DeserializationError error = deserializeJson(response_doc, response);
    
    if (!error) {
      if (response_doc.containsKey("pump_on")) {
        setPumpStatus(response_doc["pump_on"]);
      }
      if (response_doc.containsKey("pump_b_on")) {
        setPumpBStatus(response_doc["pump_b_on"]);
      }
      if (response_doc.containsKey("light_on")) {
        setLightStatus(response_doc["light_on"]);
      }
      if (response_doc.containsKey("uv_light_level")) {
        setUVLightLevel(response_doc["uv_light_level"]);
      }
      if (response_doc.containsKey("auto_watering_enabled")) {
        device_status.auto_watering_enabled = response_doc["auto_watering_enabled"];
        Serial.print("[COMMAND] Auto watering: ");
        Serial.println(response_doc["auto_watering_enabled"] ? "ON" : "OFF");
      }
      if (response_doc.containsKey("moisture_threshold")) {
        device_status.moisture_threshold = response_doc["moisture_threshold"];
        Serial.print("[COMMAND] Moisture threshold: ");
        Serial.println(device_status.moisture_threshold);
      }
      if (response_doc.containsKey("last_command")) {
        String command = response_doc["last_command"].as<String>();
        String command_time = response_doc["last_command_time"].as<String>();
        if (command.length() > 0 && command_time != last_processed_command_time) {
          last_processed_command_time = command_time;
          processRemoteCommand(command);
        }
      }
    }
  }
  
  http.end();
}

void processRemoteCommand(String command) {
  Serial.print("[COMMAND] Processing: ");
  Serial.println(command);
  
  if (command == "pump_on") {
    setPumpStatus(true);
  } 
  else if (command == "pump_off") {
    setPumpStatus(false);
  } 
  else if (command == "pump_b_on") {
    setPumpBStatus(true);
  }
  else if (command == "pump_b_off") {
    setPumpBStatus(false);
  }
  else if (command == "light_on") {
    setLightStatus(true);
  } 
  else if (command == "light_off") {
    setLightStatus(false);
  } 
  else if (command == "camera_scan" || command == "capture_disease_image") {
    Serial.println("[COMMAND] Camera scan requested. Camera ESP32 handles image upload.");
  }
  else if (command == "restart") {
    Serial.println("[COMMAND] Restarting ESP32...");
    delay(1000);
    ESP.restart();
  }
  else {
    Serial.println("[COMMAND] Unknown command!");
  }
}

// ==================== UTILITY FUNCTIONS ====================

void printSystemStatus() {
  Serial.println("\n========== SYSTEM STATUS ==========");
  Serial.print("WiFi Status: ");
  Serial.println(wifi_connected ? "Connected" : "Disconnected");
  Serial.print("Device ID: ");
  Serial.println(DEVICE_ID);
  Serial.print("Pump Status: ");
  Serial.println(device_status.pump_on ? "ON" : "OFF");
  Serial.print("Pump B Status: ");
  Serial.println(device_status.pump_b_on ? "ON" : "OFF");
  Serial.print("Light Status: ");
  Serial.println(device_status.light_on ? "ON" : "OFF");
  Serial.print("UV Level: ");
  Serial.print(device_status.uv_light_level);
  Serial.println("%");
  Serial.print("Auto Watering: ");
  Serial.println(device_status.auto_watering_enabled ? "ON" : "OFF");
  Serial.println("===================================\n");
}

/*
 * NOTES FOR USAGE:
 * 
 * 1. Replace SSID and PASSWORD with your WiFi credentials
 * 2. Replace SERVER_URL with your Flask server IP address and port
 * 3. Upload to ESP32 using Arduino IDE:
 *    - Select Board: "ESP32 Dev Module"
 *    - Select Port: COM port where ESP32 is connected
 *    - Click Upload
 * 
 * 4. Required Libraries (Install via Arduino IDE Library Manager):
 *    - WiFi.h (Built-in)
 *    - HTTPClient.h (Built-in)
 *    - ArduinoJson.h (by Benoit Blanchon)
 *    - DHT.h (by Adafruit)
 *    - Adafruit ADS1X15 (for ADS1115)
 * 
 * 5. Troubleshooting:
 *    - Check Serial Monitor at 115200 baud
 *    - Verify WiFi credentials
 *    - Check server is running and accessible
 *    - Verify firewall allows connections
 */
