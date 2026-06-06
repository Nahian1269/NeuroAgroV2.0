/*
 * ESP32 + OV6767 Still Image Uploader
 *
 * This sketch captures leaf images and uploads them to the Flask endpoint:
 *   POST /api/upload-disease-image
 * The backend returns YOLO diagnosis JSON with annotated_image_url and boxes.
 *
 * Important:
 * - Use an ESP32 board/module that exposes the camera DVP pins.
 * - OV6767 camera boards vary. Confirm the exact pin map from your camera
 *   adapter datasheet and update the CAMERA PIN DEFINITIONS section.
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include "esp_camera.h"

const char* SSID = "YOUR_SSID";
const char* PASSWORD = "YOUR_PASSWORD";
const char* SERVER_URL = "http://192.168.x.x:5001";
const char* DEVICE_ID = "ESP32_001";
const char* API_KEY = "farm-device-key";

#define CAPTURE_INTERVAL_MS 300000  // 5 minutes
#define USE_MANUAL_CAPTURE_BUTTON true
#define MANUAL_CAPTURE_PIN 0        // BOOT button on many ESP32 boards

// CAMERA PIN DEFINITIONS
// Default DVP mapping used by many ESP32 camera adapter boards.
// Change these if your OV6767 breakout uses a different pinout.
#define PWDN_GPIO_NUM    -1
#define RESET_GPIO_NUM   -1
#define XCLK_GPIO_NUM    21
#define SIOD_GPIO_NUM    26
#define SIOC_GPIO_NUM    27

#define Y9_GPIO_NUM      19
#define Y8_GPIO_NUM      18
#define Y7_GPIO_NUM      5
#define Y6_GPIO_NUM      4
#define Y5_GPIO_NUM      15
#define Y4_GPIO_NUM      14
#define Y3_GPIO_NUM      13
#define Y2_GPIO_NUM      12
#define VSYNC_GPIO_NUM   25
#define HREF_GPIO_NUM    23
#define PCLK_GPIO_NUM    22

unsigned long lastCapture = 0;
bool lastManualButtonState = HIGH;

void setup() {
  Serial.begin(115200);
  delay(500);

  connectToWiFi();
  initCamera();

  if (USE_MANUAL_CAPTURE_BUTTON) {
    pinMode(MANUAL_CAPTURE_PIN, INPUT_PULLUP);
  }

  lastCapture = millis() - CAPTURE_INTERVAL_MS;
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectToWiFi();
  }

  if (millis() - lastCapture >= CAPTURE_INTERVAL_MS) {
    captureAndUpload();
    lastCapture = millis();
  }

  if (USE_MANUAL_CAPTURE_BUTTON) {
    bool buttonState = digitalRead(MANUAL_CAPTURE_PIN);
    if (lastManualButtonState == HIGH && buttonState == LOW) {
      Serial.println("[MANUAL] Capture requested");
      captureAndUpload();
      lastCapture = millis();
    }
    lastManualButtonState = buttonState;
  }

  delay(500);
}

void connectToWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(SSID, PASSWORD);
  Serial.print("[WiFi] Connecting");

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("[WiFi] Connected: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("[WiFi] Failed to connect");
  }
}

void initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_VGA;
  config.jpeg_quality = 12;
  config.fb_count = 1;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[CAMERA] Init failed: 0x%x\n", err);
    return;
  }

  Serial.println("[CAMERA] Ready");
}

void captureAndUpload() {
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("[CAMERA] Capture failed");
    return;
  }

  String boundary = "----VerticalFarmBoundary";
  String head = "--" + boundary + "\r\n";
  head += "Content-Disposition: form-data; name=\"device_id\"\r\n\r\n";
  head += String(DEVICE_ID) + "\r\n";
  head += "--" + boundary + "\r\n";
  head += "Content-Disposition: form-data; name=\"image\"; filename=\"leaf.jpg\"\r\n";
  head += "Content-Type: image/jpeg\r\n\r\n";
  String tail = "\r\n--" + boundary + "--\r\n";

  int contentLength = head.length() + fb->len + tail.length();
  WiFiClient client;
  HTTPClient http;

  http.begin(client, String(SERVER_URL) + "/api/upload-disease-image");
  http.addHeader("Content-Type", "multipart/form-data; boundary=" + boundary);
  http.addHeader("X-API-Key", API_KEY);
  http.addHeader("Content-Length", String(contentLength));

  uint8_t* body = (uint8_t*)malloc(contentLength);
  if (!body) {
    Serial.println("[UPLOAD] Not enough memory for upload body");
    esp_camera_fb_return(fb);
    return;
  }

  memcpy(body, head.c_str(), head.length());
  memcpy(body + head.length(), fb->buf, fb->len);
  memcpy(body + head.length() + fb->len, tail.c_str(), tail.length());

  int code = http.POST(body, contentLength);
  Serial.print("[UPLOAD] HTTP ");
  Serial.println(code);
  if (code > 0) {
    Serial.println("[DIAGNOSIS]");
    Serial.println(http.getString());
  }

  free(body);
  http.end();
  esp_camera_fb_return(fb);
}
