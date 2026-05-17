"""
Скрипт для инициализации устройств и загрузки телеметрических данных из CSV датасета в БД.
Проверяет наличие данных и не дублирует их.

Использование:
    python manage.py shell < load_telemetry_data.py
    или
    python load_telemetry_data.py
"""

import os
import sys
import django
import pandas as pd
from datetime import datetime, timedelta, timezone as dt_timezone
from django.utils import timezone

# Если запущено как скрипт, установим Django
if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iot_hub.config.settings')
    django.setup()

from iot_hub.apps.devices.models import Device, DeviceType, DeviceMetric
from iot_hub.apps.telemetry.models import Telemetry
from django.contrib.auth.models import User


def create_device_types_and_devices():
    """Создает типы устройств и демо-устройства если их нет."""
    
    # Проверяем есть ли уже конкретные устройства по серийным номерам
    required_devices = ['TEMP-001', 'TEMP-002', 'TEMP-003', 'HUM-001', 'HUM-002', 
                       'PRES-001', 'PLUG-001', 'PLUG-002', 'PLUG-003', 'LED-001']
    existing_count = Device.objects.filter(serial_number__in=required_devices).count()
    
    if existing_count == len(required_devices):
        print("✅ Все устройства уже созданы ({} шт.)".format(existing_count))
        return False
    
    print("📱 Создаю типы устройств и демо-устройства...")
    
    # Создание типов устройств
    device_types = [
        {'name': 'Датчик температуры', 'description': 'Умный датчик для измерения температуры', 'manufacturer': 'Generic'},
        {'name': 'Датчик влажности', 'description': 'Умный датчик для измерения влажности воздуха', 'manufacturer': 'Generic'},
        {'name': 'Датчик давления', 'description': 'Умный датчик для измерения атмосферного давления', 'manufacturer': 'Generic'},
        {'name': 'Умная розетка', 'description': 'Умная розетка для управления потреблением энергии', 'manufacturer': 'Generic'},
        {'name': 'LED лампа', 'description': 'Умная LED лампа с регулировкой яркости и цвета', 'manufacturer': 'Generic'},
        {'name': 'Контроллер', 'description': 'IoT контроллер для управления другими устройствами', 'manufacturer': 'Generic'},
    ]
    
    type_map = {}
    for device_type in device_types:
        dt, _ = DeviceType.objects.get_or_create(
            name=device_type['name'],
            defaults={
                'description': device_type['description'],
                'manufacturer': device_type['manufacturer'],
            }
        )
        type_map[device_type['name']] = dt
    
    # Получаем первого (администратора) или создаем
    owner = User.objects.filter(is_superuser=True).first()
    if not owner:
        owner = User.objects.first()
    
    # Создание демонстрационных устройств и метрик
    demo_devices = [
        # 3 датчика температуры
        {
            'name': 'Датчик температуры - Гостиная (T1)',
            'serial_number': 'TEMP-001',
            'device_type': type_map['Датчик температуры'],
            'location_name': 'Гостиная',
            'metadata': {'csv_column': 'T1', 'period_days': 30},
            'metrics': [
                {'metric_type': 'temperature', 'name': 'Температура', 'unit': '°C', 'min_value': -10, 'max_value': 50}
            ]
        },
        {
            'name': 'Датчик температуры - Ванная (T8)',
            'serial_number': 'TEMP-002',
            'device_type': type_map['Датчик температуры'],
            'location_name': 'Ванная',
            'metadata': {'csv_column': 'T8', 'period_days': 30},
            'metrics': [
                {'metric_type': 'temperature', 'name': 'Температура', 'unit': '°C', 'min_value': -10, 'max_value': 50}
            ]
        },
        {
            'name': 'Датчик температуры - Улица (T_out)',
            'serial_number': 'TEMP-003',
            'device_type': type_map['Датчик температуры'],
            'location_name': 'Улица',
            'metadata': {'csv_column': 'T_out', 'period_days': 30},
            'metrics': [
                {'metric_type': 'temperature', 'name': 'Температура', 'unit': '°C', 'min_value': -20, 'max_value': 40}
            ]
        },
        # 2 датчика влажности
        {
            'name': 'Датчик влажности - Гостиная (RH_1)',
            'serial_number': 'HUM-001',
            'device_type': type_map['Датчик влажности'],
            'location_name': 'Гостиная',
            'metadata': {'csv_column': 'RH_1', 'period_days': 30},
            'metrics': [
                {'metric_type': 'humidity', 'name': 'Влажность', 'unit': '%', 'min_value': 0, 'max_value': 100}
            ]
        },
        {
            'name': 'Датчик влажности - Кухня (RH_3)',
            'serial_number': 'HUM-002',
            'device_type': type_map['Датчик влажности'],
            'location_name': 'Кухня',
            'metadata': {'csv_column': 'RH_3', 'period_days': 30},
            'metrics': [
                {'metric_type': 'humidity', 'name': 'Влажность', 'unit': '%', 'min_value': 0, 'max_value': 100}
            ]
        },
        # 1 датчик давления
        {
            'name': 'Датчик давления',
            'serial_number': 'PRES-001',
            'device_type': type_map['Датчик давления'],
            'location_name': 'Основной',
            'metadata': {'csv_column': 'Press_mm_hg', 'period_days': 30},
            'metrics': [
                {'metric_type': 'custom', 'name': 'Давление', 'unit': 'мм рт.ст.', 'min_value': 700, 'max_value': 800}
            ]
        },
        # 3 умные розетки
        {
            'name': 'Умная розетка - Период 1',
            'serial_number': 'PLUG-001',
            'device_type': type_map['Умная розетка'],
            'location_name': 'Жилая комната',
            'metadata': {'csv_column': 'Appliances', 'period_days': 30, 'period_number': 1},
            'metrics': [
                {'metric_type': 'power', 'name': 'Энергопотребление', 'unit': 'Wh', 'min_value': 0, 'max_value': 2000}
            ]
        },
        {
            'name': 'Умная розетка - Период 2',
            'serial_number': 'PLUG-002',
            'device_type': type_map['Умная розетка'],
            'location_name': 'Спальня',
            'metadata': {'csv_column': 'Appliances', 'period_days': 30, 'period_number': 2},
            'metrics': [
                {'metric_type': 'power', 'name': 'Энергопотребление', 'unit': 'Wh', 'min_value': 0, 'max_value': 2000}
            ]
        },
        {
            'name': 'Умная розетка - Период 3',
            'serial_number': 'PLUG-003',
            'device_type': type_map['Умная розетка'],
            'location_name': 'Кухня',
            'metadata': {'csv_column': 'Appliances', 'period_days': 30, 'period_number': 3},
            'metrics': [
                {'metric_type': 'power', 'name': 'Энергопотребление', 'unit': 'Wh', 'min_value': 0, 'max_value': 2000}
            ]
        },
        # 1 LED лампа
        {
            'name': 'LED лампа - Гостиная',
            'serial_number': 'LED-001',
            'device_type': type_map['LED лампа'],
            'location_name': 'Гостиная',
            'metadata': {'csv_column': 'lights', 'period_days': 30},
            'metrics': [
                {'metric_type': 'custom', 'name': 'Освещенность', 'unit': 'Wh', 'min_value': 0, 'max_value': 800}
            ]
        },
    ]
    
    # Создание устройств и метрик
    for device_data in demo_devices:
        metrics_data = device_data.pop('metrics')
        device, _ = Device.objects.get_or_create(
            serial_number=device_data['serial_number'],
            defaults={
                'name': device_data['name'],
                'device_type': device_data['device_type'],
                'location_name': device_data.get('location_name', ''),
                'metadata': device_data.get('metadata', {}),
                'owner': owner,
                'status': 'active',
                'is_active': True,
                'installation_date': timezone.now(),
            }
        )
        
        # Создание метрик для устройства
        for metric_data in metrics_data:
            DeviceMetric.objects.get_or_create(
                device=device,
                metric_type=metric_data['metric_type'],
                defaults={
                    'name': metric_data['name'],
                    'unit': metric_data.get('unit', ''),
                    'min_value': metric_data.get('min_value'),
                    'max_value': metric_data.get('max_value'),
                    'is_active': True,
                }
            )
    
    print(f"✅ Создано 10 устройств с метриками")
    return True


def load_telemetry_data():
    """Загружает данные телеметрии из CSV в БД если их нет."""
    
    # Проверяем есть ли уже полная телеметрия (300 записей)
    if Telemetry.objects.count() >= 300:
        print("✅ Телеметрия уже загружена ({} записей)".format(Telemetry.objects.count()))
        return False
    
    csv_file = 'energydata_complete.csv'
    
    if not os.path.exists(csv_file):
        print(f"⚠️  Файл {csv_file} не найден, пропускаю загрузку телеметрии")
        return False
    
    print(f"📊 Загружаю телеметрические данные из {csv_file}...")
    df = pd.read_csv(csv_file)
    
    # Преобразуем дату
    df['date'] = pd.to_datetime(df['date'])
    
    # Маппинг устройств на столбцы CSV
    device_mappings = [
        # Датчики температуры
        {'csv_column': 'T1', 'serial_number': 'TEMP-001', 'unit': '°C'},
        {'csv_column': 'T8', 'serial_number': 'TEMP-002', 'unit': '°C'},
        {'csv_column': 'T_out', 'serial_number': 'TEMP-003', 'unit': '°C'},
        
        # Датчики влажности
        {'csv_column': 'RH_1', 'serial_number': 'HUM-001', 'unit': '%'},
        {'csv_column': 'RH_3', 'serial_number': 'HUM-002', 'unit': '%'},
        
        # Датчик давления
        {'csv_column': 'Press_mm_hg', 'serial_number': 'PRES-001', 'unit': 'мм рт.ст.'},
        
        # Умные розетки (одна колонка, но разные периоды 30 дней)
        {'csv_column': 'Appliances', 'serial_number': 'PLUG-001', 'unit': 'Wh', 'period_number': 1},
        {'csv_column': 'Appliances', 'serial_number': 'PLUG-002', 'unit': 'Wh', 'period_number': 2},
        {'csv_column': 'Appliances', 'serial_number': 'PLUG-003', 'unit': 'Wh', 'period_number': 3},
        
        # LED лампа
        {'csv_column': 'lights', 'serial_number': 'LED-001', 'unit': 'Wh'},
    ]
    
    # Загружаем данные для каждого устройства
    start_date = pd.Timestamp(2016, 1, 11)  # Начало датасета
    
    for mapping in device_mappings:
        serial_number = mapping['serial_number']
        csv_column = mapping['csv_column']
        unit = mapping['unit']
        period_number = mapping.get('period_number', 1)
        
        try:
            device = Device.objects.get(serial_number=serial_number)
        except Device.DoesNotExist:
            continue
        
        # Определяем диапазон дат для периода (30 дней)
        period_start = start_date + timedelta(days=(period_number - 1) * 30)
        period_end = period_start + timedelta(days=29)  # 30 дней
        
        # Фильтруем данные для периода
        period_data = df[(df['date'] >= period_start) & (df['date'] <= period_end)].copy()
        
        if period_data.empty:
            continue
        
        # Усредняем по дням - используем полную дату
        daily_avg = period_data.groupby(period_data['date'].dt.date)[csv_column].agg(['mean', 'std', 'count'])
        
        # Получаем метрику устройства
        try:
            metric = device.metrics.first()
            if not metric:
                continue
        except:
            continue
        
        telemetries = []
        
        # Создаем записи телеметрии
        for day, row in daily_avg.iterrows():
            try:
                # Используем дату из дня как время записи (полдень) в UTC
                naive_dt = datetime.combine(day, datetime.min.time().replace(hour=12, minute=0))
                recorded_at = naive_dt.replace(tzinfo=dt_timezone.utc)
                
                value = float(row['mean'])
                
                # Обрабатываем NaN значения
                std_val = float(row['std']) if not pd.isna(row['std']) else 0
                count_val = int(row['count']) if not pd.isna(row['count']) else 0
                
                telemetries.append(
                    Telemetry(
                        device=device,
                        metric=metric,
                        value=value,
                        unit=unit,
                        status='ok',
                        recorded_at=recorded_at,
                        raw_data={
                            'std': std_val,
                            'count': count_val,
                            'csv_column': csv_column,
                        }
                    )
                )
            except Exception as e:
                continue
        
        # Массовая вставка
        if telemetries:
            Telemetry.objects.bulk_create(telemetries, batch_size=1000)
    
    print(f"✅ Телеметрия загружена ({Telemetry.objects.count()} записей)")
    return True


def main():
    """Главная функция инициализации."""
    print("\n=== ИНИЦИАЛИЗАЦИЯ БД ===\n")
    
    # Создаем устройства
    create_device_types_and_devices()
    
    # Загружаем телеметрию
    load_telemetry_data()
    
    print("\n✅ Инициализация завершена!\n")


if __name__ == '__main__':
    main()
