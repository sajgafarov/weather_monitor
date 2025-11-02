#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
#include <Wire.h>
#include <GyverBME280.h>
#include <ArduinoJson.h>

const char* ssid = "ваш wifi";
const char* password = "пароль от вашего wifi";
const char* serverURL = "ip вашего сервера/api/data";

GyverBME280 bme;

void setup() {
  Serial.begin(115200);
  
  // Инициализация датчика
  if (!bme.begin()) {
    Serial.println("BME280 не найден!");
    while(1);
  }
  
  // Подключение к WiFi
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.print(".");
  }
  Serial.println("Подключено!");
}

void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    WiFiClient client;
    HTTPClient http;
    
    float t = bme.readTemperature();
    float h = bme.readHumidity();
    float p = bme.readPressure() / 133.3F; // мм рт.ст.

    String json = "{\"temperature\":" + String(t, 1) + 
                  ",\"humidity\":" + String(h, 1) + 
                  ",\"pressure\":" + String(p, 1) + 
                  ",\"device_id\":\"esp8266\"}";

    http.begin(client, serverURL);
    http.addHeader("Content-Type", "application/json");
    
    int code = http.POST(json);
    Serial.print("Код ответа: ");
    Serial.println(code);
    
    http.end();
  }
  
  delay(300000); // Ждем 5 минут
}