
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
#include <Wire.h>
#include <GyverBME280.h>
#include <ArduinoJson.h>

const char* ssid = "your wifi name";
const char* password = "your wifi password";
const char* serverURL = "your ip/api/data";

GyverBME280 bme;

void setup() {
  Serial.begin(115200);
  
  // Sensor initialization
  if (!bme.begin()) {
    Serial.println("BME280 not found!");
    while(1);
  }
  
  // WiFi connection
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.print(".");
  }
  Serial.println("Connected!");
}

void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    WiFiClient client;
    HTTPClient http;
    
    float t = bme.readTemperature();
    float h = bme.readHumidity();
    float p = bme.readPressure() / 133.3F; // mmHg

    String json = "{\"temperature\":" + String(t, 1) + 
                  ",\"humidity\":" + String(h, 1) + 
                  ",\"pressure\":" + String(p, 1) + 
                  ",\"device_id\":\"esp8266\"}";

    http.begin(client, serverURL);
    http.addHeader("Content-Type", "application/json");
    
    int code = http.POST(json);
    Serial.print("Response code: ");
    Serial.println(code);
    
    http.end();
  }
  
  delay(300000); // Wait 5 minutes
}