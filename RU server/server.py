from flask import Flask, request, jsonify, send_from_directory
import sqlite3
from datetime import datetime, timedelta
from flask_cors import CORS
import math
import os

app = Flask(__name__)
CORS(app)

# Глобальные счетчики (только API вызовы)
api_calls = {
    'data': 0,
    'current': 0, 
    'history': 0,
    'forecast': 0,
    'simple_chart': 0
}

# Файл для хранения статистики посещений
VISITS_FILE = 'visits.txt'

def get_db_connection():
    conn = sqlite3.connect('meteo.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS weather_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            temperature REAL NOT NULL,
            humidity REAL NOT NULL,
            pressure REAL NOT NULL,
            timestamp TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()
    print("База данных инициализирована!")

# Функция для инициализации файла посещений
def init_visits_file():
    if not os.path.exists(VISITS_FILE):
        with open(VISITS_FILE, 'w') as f:
            f.write('0')
        print("Файл статистики посещений создан!")

# Функция для чтения количества посещений
def read_visits():
    try:
        with open(VISITS_FILE, 'r') as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return 0

# Функция для записи количества посещений
def write_visits(count):
    with open(VISITS_FILE, 'w') as f:
        f.write(str(count))

# Функция для увеличения счетчика посещений
def increment_visits():
    visits = read_visits()
    visits += 1
    write_visits(visits)
    return visits

# Функция для расчета ощущаемой температуры (Heat Index)
def calculate_feels_like(temperature, humidity):
    """
    Рассчитывает ощущаемую температуру (Heat Index) по формуле NOAA
    Работает для температур выше 20°C
    """
    if temperature < 20:
        return temperature  # Для низких температур используем фактическую температуру
    
    # Формула Heat Index (NOAA)
    c1 = -8.78469475556
    c2 = 1.61139411
    c3 = 2.33854883889
    c4 = -0.14611605
    c5 = -0.012308094
    c6 = -0.0164248277778
    c7 = 0.002211732
    c8 = 0.00072546
    c9 = -0.000003582
    
    T = temperature
    R = humidity
    
    feels_like = (c1 + c2 * T + c3 * R + c4 * T * R + 
                 c5 * T * T + c6 * R * R + 
                 c7 * T * T * R + c8 * T * R * R + 
                 c9 * T * T * R * R)
    
    return round(feels_like, 1)

# Главная страница
@app.route('/')
def index():
    # Увеличиваем счетчик посещений при каждом заходе на главную страницу
    total_visits = increment_visits()
    print(f"🌐 Новый посетитель! Всего посещений: {total_visits}")
    return send_from_directory('.', 'index.html')

# API для получения статистики (только API вызовы)
@app.route('/api/stats')
def get_stats():
    total_visits = read_visits()
    return jsonify({
        'api_calls': api_calls,
        'total_api_calls': sum(api_calls.values()),
        'total_visits': total_visits
    })

# Получение данных от ESP8266
@app.route('/api/data', methods=['POST'])
def receive_data():
    global api_calls
    api_calls['data'] += 1
    
    try:
        data = request.get_json()
        print(f"📨 Данные от ESP #{api_calls['data']}: {data}")
        
        temperature = data.get('temperature')
        humidity = data.get('humidity')
        pressure = data.get('pressure')
        timestamp = datetime.now().isoformat()

        conn = get_db_connection()
        conn.execute('INSERT INTO weather_data (temperature, humidity, pressure, timestamp) VALUES (?, ?, ?, ?)',
                    (temperature, humidity, pressure, timestamp))
        conn.commit()
        conn.close()

        return jsonify({"status": "success", "message": "Data saved"}), 201
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Текущие данные
@app.route('/api/current')
def get_current_data():
    global api_calls
    api_calls['current'] += 1
    
    conn = get_db_connection()
    data = conn.execute('SELECT * FROM weather_data ORDER BY timestamp DESC LIMIT 1').fetchone()
    conn.close()

    if data is None:
        return jsonify({"error": "No data available"}), 404

    data_dict = dict(data)
    # Добавляем ощущаемую температуру
    data_dict['feels_like'] = calculate_feels_like(data_dict['temperature'], data_dict['humidity'])
    
    return jsonify(data_dict)

# Упрощенные данные для графика (4 точки - каждые 30 минут)
# Упрощенные данные для графика (4 точки - каждые 30 минут за последние 1.5 часа)
@app.route('/api/simple_chart')
def get_simple_chart():
    global api_calls
    api_calls['simple_chart'] += 1
    
    conn = get_db_connection()
    
    # Получаем данные за последние 2 часа
    two_hours_ago = (datetime.now() - timedelta(hours=2)).isoformat()
    
    data = conn.execute('''
        SELECT * FROM weather_data 
        WHERE timestamp >= ?
        ORDER BY timestamp DESC
    ''', (two_hours_ago,)).fetchall()
    conn.close()

    if not data:
        return jsonify([])

    # Преобразуем данные и добавляем ощущаемую температуру
    all_data = []
    for row in data:
        row_dict = dict(row)
        row_dict['feels_like'] = calculate_feels_like(row_dict['temperature'], row_dict['humidity'])
        all_data.append(row_dict)

    # Создаем целевые временные точки с точностью до секунд
    now = datetime.now()
    target_times = [
        now - timedelta(hours=1, minutes=30),  # 1.5 часа назад
        now - timedelta(hours=1),              # 1 час назад  
        now - timedelta(minutes=30),           # 30 минут назад
        now                                    # Сейчас
    ]

    chart_data = []
    
    for target_time in target_times:
        closest_record = None
        min_time_diff = timedelta(minutes=10)  # Погрешность 10 минут
        
        for record in all_data:
            record_time = datetime.fromisoformat(record['timestamp'])
            time_diff = abs(record_time - target_time)
            
            if time_diff < min_time_diff:
                min_time_diff = time_diff
                closest_record = record
        
        if closest_record:
            record_time = datetime.fromisoformat(closest_record['timestamp'])
            
            # Определяем метку времени
            if target_time == target_times[3]:  # Сейчас
                time_label = "Сейчас"
                time_suffix = ""
            else:
                time_diff = now - record_time
                hours = int(time_diff.total_seconds() // 3600)
                minutes = int((time_diff.total_seconds() % 3600) // 60)
                
                if hours > 0:
                    time_label = f"{hours} ч {minutes} мин"
                else:
                    time_label = f"{minutes} мин"
                time_suffix = "назад"
            
            chart_data.append({
                "label": time_label,
                "time_suffix": time_suffix,
                "display_time": record_time.strftime('%H:%M'),
                "temperature": closest_record['temperature'],
                "humidity": closest_record['humidity'],
                "pressure": closest_record['pressure'],
                "feels_like": closest_record['feels_like'],
                "full_timestamp": closest_record['timestamp'],
                "seconds_ago": int((now - record_time).total_seconds())
            })

    # Если не нашли все 4 точки, дополняем последними доступными данными
    if len(chart_data) < 4:
        # Берем самые свежие данные для недостающих точек
        time_labels = ['1.5 ч', '1 ч', '30 мин', 'Сейчас']
        time_suffixes = ['назад', 'назад', 'назад', '']
        
        for i in range(4 - len(chart_data)):
            if all_data:
                record = all_data[i] if i < len(all_data) else all_data[0]
                record_time = datetime.fromisoformat(record['timestamp'])
                time_diff = now - record_time
                
                if i == 3:  # Последняя точка - "Сейчас"
                    label = "Сейчас"
                    suffix = ""
                else:
                    hours = int(time_diff.total_seconds() // 3600)
                    minutes = int((time_diff.total_seconds() % 3600) // 60)
                    
                    if hours > 0:
                        label = f"{hours} ч {minutes} мин"
                    else:
                        label = f"{minutes} мин"
                    suffix = "назад"
                
                chart_data.append({
                    "label": label,
                    "time_suffix": suffix,
                    "display_time": record_time.strftime('%H:%M'),
                    "temperature": record['temperature'],
                    "humidity": record['humidity'],
                    "pressure": record['pressure'],
                    "feels_like": record['feels_like'],
                    "full_timestamp": record['timestamp'],
                    "seconds_ago": int(time_diff.total_seconds())
                })

    # Сортируем от старых к новым
    chart_data.sort(key=lambda x: x['full_timestamp'])
    
    return jsonify(chart_data)

# История данных
@app.route('/api/history')
def get_history():
    global api_calls
    api_calls['history'] += 1
    
    conn = get_db_connection()
    data = conn.execute('SELECT * FROM weather_data ORDER BY timestamp DESC LIMIT 24').fetchall()
    conn.close()

    history_list = []
    for row in data:
        row_dict = dict(row)
        row_dict['feels_like'] = calculate_feels_like(row_dict['temperature'], row_dict['humidity'])
        
        history_list.append({
            "temperature": row_dict['temperature'],
            "humidity": row_dict['humidity'],
            "pressure": row_dict['pressure'],
            "feels_like": row_dict['feels_like'],
            "timestamp": row_dict['timestamp']
        })
    
    history_list.reverse()
    return jsonify(history_list)

# Прогноз
@app.route('/api/forecast')
def get_forecast():
    global api_calls
    api_calls['forecast'] += 1
    
    conn = get_db_connection()
    data = conn.execute('SELECT pressure FROM weather_data ORDER BY timestamp DESC LIMIT 2').fetchall()
    conn.close()

    if len(data) < 2:
        return jsonify({"forecast": "Недостаточно данных"})

    current_pressure = data[0]['pressure']
    previous_pressure = data[1]['pressure']
    pressure_diff = current_pressure - previous_pressure

    if pressure_diff > 2.0:
        forecast = "📈 Улучшение погоды"
        forecast_description = "Атмосферное давление растет, ожидается ясная погода"
    elif pressure_diff < -2.0:
        forecast = "📉 Ухудшение погоды"
        forecast_description = "Атмосферное давление падает, возможны осадки"
    else:
        forecast = "➡️ Без изменений"
        forecast_description = "Погода стабильна, значительных изменений не ожидается"

    return jsonify({
        "forecast": forecast,
        "description": forecast_description,
        "pressure_change": round(pressure_diff, 1)
    })

# Сброс статистики (для тестов)
@app.route('/api/reset_stats', methods=['DELETE'])
def reset_stats():
    global api_calls
    api_calls = {'data': 0, 'current': 0, 'history': 0, 'forecast': 0, 'simple_chart': 0}
    # Также сбрасываем статистику посещений
    write_visits(0)
    return jsonify({"status": "success", "message": "Statistics reset"})

# API для получения только статистики посещений
@app.route('/api/visits')
def get_visits():
    total_visits = read_visits()
    return jsonify({
        'total_visits': total_visits
    })

if __name__ == '__main__':
    init_db()
    init_visits_file()
    print("Сервер запущен!")
    # Замени на эти настройки для продакшена:
    app.run(host='0.0.0.0', port=5000, debug=False)