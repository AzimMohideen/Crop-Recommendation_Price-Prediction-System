/*
  ESP32 POST sensor data to Flask backend
  Sends temperature, humidity, heat index, soil analog %, and soil digital
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include "DHT.h"

#define DHTPIN 4
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

#define SOIL_ANALOG 34   // AOUT → GPIO34 (ADC)
#define SOIL_DIGITAL 17  // DOUT → GPIO16 (any free digital pin)

const char* ssid = "Your SSID";
const char* password = "Your Password";

// Flask server IP and port (change to your PC's IP)
const char* serverUrl = "your-server-ip:5000/sensor-data";
const char* apiKey = "your api key";  // must match SENSOR_API_KEY in Flask
void setup() {
  Serial.begin(115200);
  dht.begin();
  pinMode(SOIL_DIGITAL, INPUT);

  delay(1000);
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 30) {
    delay(500);
    Serial.print(".");
    tries++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nConnected! IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nFailed to connect WiFi");
  }
}

void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    float temperature = dht.readTemperature();
    float humidity = dht.readHumidity();
    float heatIndex = dht.computeHeatIndex(temperature, humidity, false); // false = Celsius

    int soilAnalog = analogRead(SOIL_ANALOG);
    int soilMoisture = map(soilAnalog, 4095, 0, 0, 100);  // 0–100 %

    int soilDigital = digitalRead(SOIL_DIGITAL);
    String soilStatus = (soilDigital == LOW) ? "Wet" : "Dry";

    // Fallbacks if sensor fails
    if (isnan(temperature) || isnan(humidity)) {
      temperature = 0.0;
      humidity = 0.0;
      heatIndex = 0.0;
    }

    // Prepare JSON payload
    String json = "{";
    json += "\"temperature\":" + String(temperature, 1) + ",";
    json += "\"humidity\":" + String(humidity, 0) + ",";
    json += "\"heat_index\":" + String(heatIndex, 1) + ",";
    json += "\"soil_analog\":" + String(soilMoisture) + ",";
    json += "\"soil_digital\":\"" + soilStatus + "\"";
    json += "}";

    Serial.println("Posting: " + json);

    HTTPClient http;
    http.begin(serverUrl);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-API-KEY", apiKey);
    int code = http.POST(json);
    if (code > 0) {
      Serial.printf("POST %d\n", code);
    } else {
      Serial.printf("POST failed: %s\n", http.errorToString(code).c_str());
    }
    http.end();
  } else {
    Serial.println("WiFi not connected");
  }

  delay(3000); // send every 3 seconds
}
