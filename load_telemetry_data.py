"""
Скрипт для инициализации пользователей, устройств и загрузки телеметрии из CSV.
Проверяет наличие данных и не дублирует их.
"""

import os
import sys
import django
import pandas as pd
from datetime import datetime, timedelta, timezone as dt_timezone
from django.utils import timezone

if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iot_hub.config.settings')
    django.setup()

from django.contrib.auth.models import User
from iot_hub.apps.accounts.models import UserRole, UserProfile
from iot_hub.apps.devices.models import Device, DeviceType, DeviceMetric
from iot_hub.apps.telemetry.models import Telemetry


# ──────────────────────────────────────────────
# Описание пользователей и их устройств
# ──────────────────────────────────────────────

CSV_START = pd.Timestamp(2016, 1, 11)

USERS_CONFIG = [
    {
        'username': 'operator1',
        'email': 'operator1@mail.ru',
        'password': 'operator123',
        'first_name': 'Иван',
        'last_name': 'Петров',
        'role': 'operator',
        'period_offset_days': 30,   # дни 31-60 от начала датасета
        'devices': [
            {
                'name': 'Датчик температуры - Спальня (T2)',
                'serial_number': 'TEMP-004',
                'type': 'Датчик температуры',
                'location_name': 'Спальня',
                'csv_column': 'T2',
                'metrics': [{'metric_type': 'temperature', 'name': 'Температура', 'unit': '°C', 'min_value': -10, 'max_value': 50}],
            },
            {
                'name': 'Датчик температуры - Детская (T5)',
                'serial_number': 'TEMP-005',
                'type': 'Датчик температуры',
                'location_name': 'Детская',
                'csv_column': 'T5',
                'metrics': [{'metric_type': 'temperature', 'name': 'Температура', 'unit': '°C', 'min_value': -10, 'max_value': 50}],
            },
            {
                'name': 'Датчик влажности - Спальня (RH_2)',
                'serial_number': 'HUM-003',
                'type': 'Датчик влажности',
                'location_name': 'Спальня',
                'csv_column': 'RH_2',
                'metrics': [{'metric_type': 'humidity', 'name': 'Влажность', 'unit': '%', 'min_value': 0, 'max_value': 100}],
            },
            {
                'name': 'Датчик влажности - Детская (RH_5)',
                'serial_number': 'HUM-004',
                'type': 'Датчик влажности',
                'location_name': 'Детская',
                'csv_column': 'RH_5',
                'metrics': [{'metric_type': 'humidity', 'name': 'Влажность', 'unit': '%', 'min_value': 0, 'max_value': 100}],
            },
            {
                'name': 'Метеостанция - Скорость ветра',
                'serial_number': 'WIND-001',
                'type': 'Контроллер',
                'location_name': 'Крыша',
                'csv_column': 'Windspeed',
                'metrics': [{'metric_type': 'custom', 'name': 'Скорость ветра', 'unit': 'м/с', 'min_value': 0, 'max_value': 50}],
            },
        ],
    },
    {
        'username': 'operator2',
        'email': 'operator2@mail.ru',
        'password': 'operator123',
        'first_name': 'Мария',
        'last_name': 'Иванова',
        'role': 'operator',
        'period_offset_days': 60,   # дни 61-90
        'devices': [
            {
                'name': 'Датчик температуры - Столовая (T3)',
                'serial_number': 'TEMP-006',
                'type': 'Датчик температуры',
                'location_name': 'Столовая',
                'csv_column': 'T3',
                'metrics': [{'metric_type': 'temperature', 'name': 'Температура', 'unit': '°C', 'min_value': -10, 'max_value': 50}],
            },
            {
                'name': 'Датчик температуры - Детская 2 (T6)',
                'serial_number': 'TEMP-007',
                'type': 'Датчик температуры',
                'location_name': 'Детская 2',
                'csv_column': 'T6',
                'metrics': [{'metric_type': 'temperature', 'name': 'Температура', 'unit': '°C', 'min_value': -10, 'max_value': 50}],
            },
            {
                'name': 'Датчик влажности - Столовая (RH_4)',
                'serial_number': 'HUM-005',
                'type': 'Датчик влажности',
                'location_name': 'Столовая',
                'csv_column': 'RH_4',
                'metrics': [{'metric_type': 'humidity', 'name': 'Влажность', 'unit': '%', 'min_value': 0, 'max_value': 100}],
            },
            {
                'name': 'Датчик влажности - Детская 2 (RH_6)',
                'serial_number': 'HUM-006',
                'type': 'Датчик влажности',
                'location_name': 'Детская 2',
                'csv_column': 'RH_6',
                'metrics': [{'metric_type': 'humidity', 'name': 'Влажность', 'unit': '%', 'min_value': 0, 'max_value': 100}],
            },
            {
                'name': 'Датчик давления - Период 2',
                'serial_number': 'PRES-002',
                'type': 'Датчик давления',
                'location_name': 'Основной',
                'csv_column': 'Press_mm_hg',
                'metrics': [{'metric_type': 'custom', 'name': 'Давление', 'unit': 'мм рт.ст.', 'min_value': 700, 'max_value': 800}],
            },
        ],
    },
    {
        'username': 'client1',
        'email': 'client1@mail.ru',
        'password': 'client123',
        'first_name': 'Алексей',
        'last_name': 'Сидоров',
        'role': 'client',
        'period_offset_days': 90,   # дни 91-120
        'devices': [
            {
                'name': 'Датчик температуры - Офис (T4)',
                'serial_number': 'TEMP-008',
                'type': 'Датчик температуры',
                'location_name': 'Офис',
                'csv_column': 'T4',
                'metrics': [{'metric_type': 'temperature', 'name': 'Температура', 'unit': '°C', 'min_value': -10, 'max_value': 50}],
            },
            {
                'name': 'Датчик температуры - Коридор (T7)',
                'serial_number': 'TEMP-009',
                'type': 'Датчик температуры',
                'location_name': 'Коридор',
                'csv_column': 'T7',
                'metrics': [{'metric_type': 'temperature', 'name': 'Температура', 'unit': '°C', 'min_value': -10, 'max_value': 50}],
            },
            {
                'name': 'Датчик влажности - Офис (RH_7)',
                'serial_number': 'HUM-007',
                'type': 'Датчик влажности',
                'location_name': 'Офис',
                'csv_column': 'RH_7',
                'metrics': [{'metric_type': 'humidity', 'name': 'Влажность', 'unit': '%', 'min_value': 0, 'max_value': 100}],
            },
            {
                'name': 'Датчик влажности - Серверная (RH_9)',
                'serial_number': 'HUM-008',
                'type': 'Датчик влажности',
                'location_name': 'Серверная',
                'csv_column': 'RH_9',
                'metrics': [{'metric_type': 'humidity', 'name': 'Влажность', 'unit': '%', 'min_value': 0, 'max_value': 100}],
            },
            {
                'name': 'Датчик точки росы',
                'serial_number': 'DEW-001',
                'type': 'Датчик температуры',
                'location_name': 'Улица',
                'csv_column': 'Tdewpoint',
                'metrics': [{'metric_type': 'temperature', 'name': 'Точка росы', 'unit': '°C', 'min_value': -30, 'max_value': 30}],
            },
        ],
    },
]

# Серийные номера устройств админа (из старой логики)
ADMIN_SERIALS = ['TEMP-001', 'TEMP-002', 'TEMP-003', 'HUM-001', 'HUM-002',
                 'PRES-001', 'PLUG-001', 'PLUG-002', 'PLUG-003', 'LED-001']


# ──────────────────────────────────────────────
# Функции
# ──────────────────────────────────────────────

def get_or_create_device_type_map():
    device_types = [
        {'name': 'Датчик температуры', 'description': 'Умный датчик для измерения температуры', 'manufacturer': 'Generic'},
        {'name': 'Датчик влажности', 'description': 'Умный датчик для измерения влажности воздуха', 'manufacturer': 'Generic'},
        {'name': 'Датчик давления', 'description': 'Умный датчик для измерения атмосферного давления', 'manufacturer': 'Generic'},
        {'name': 'Умная розетка', 'description': 'Умная розетка для управления потреблением энергии', 'manufacturer': 'Generic'},
        {'name': 'LED лампа', 'description': 'Умная LED лампа с регулировкой яркости и цвета', 'manufacturer': 'Generic'},
        {'name': 'Контроллер', 'description': 'IoT контроллер для управления другими устройствами', 'manufacturer': 'Generic'},
    ]
    type_map = {}
    for dt_data in device_types:
        dt, _ = DeviceType.objects.get_or_create(
            name=dt_data['name'],
            defaults={'description': dt_data['description'], 'manufacturer': dt_data['manufacturer']}
        )
        type_map[dt_data['name']] = dt
    return type_map


def create_device_types_and_devices():
    """Создаёт типы устройств и демо-устройства админа если их нет."""

    existing_count = Device.objects.filter(serial_number__in=ADMIN_SERIALS).count()
    if existing_count == len(ADMIN_SERIALS):
        print("✅ Все устройства уже созданы ({} шт.)".format(existing_count))
        return False

    print("📱 Создаю типы устройств и демо-устройства...")

    type_map = get_or_create_device_type_map()

    owner = User.objects.filter(is_superuser=True).first() or User.objects.first()

    demo_devices = [
        {'name': 'Датчик температуры - Гостиная (T1)', 'serial_number': 'TEMP-001',
         'device_type': type_map['Датчик температуры'], 'location_name': 'Гостиная',
         'metadata': {'csv_column': 'T1', 'period_days': 30},
         'metrics': [{'metric_type': 'temperature', 'name': 'Температура', 'unit': '°C', 'min_value': -10, 'max_value': 50}]},
        {'name': 'Датчик температуры - Ванная (T8)', 'serial_number': 'TEMP-002',
         'device_type': type_map['Датчик температуры'], 'location_name': 'Ванная',
         'metadata': {'csv_column': 'T8', 'period_days': 30},
         'metrics': [{'metric_type': 'temperature', 'name': 'Температура', 'unit': '°C', 'min_value': -10, 'max_value': 50}]},
        {'name': 'Датчик температуры - Улица (T_out)', 'serial_number': 'TEMP-003',
         'device_type': type_map['Датчик температуры'], 'location_name': 'Улица',
         'metadata': {'csv_column': 'T_out', 'period_days': 30},
         'metrics': [{'metric_type': 'temperature', 'name': 'Температура', 'unit': '°C', 'min_value': -20, 'max_value': 40}]},
        {'name': 'Датчик влажности - Гостиная (RH_1)', 'serial_number': 'HUM-001',
         'device_type': type_map['Датчик влажности'], 'location_name': 'Гостиная',
         'metadata': {'csv_column': 'RH_1', 'period_days': 30},
         'metrics': [{'metric_type': 'humidity', 'name': 'Влажность', 'unit': '%', 'min_value': 0, 'max_value': 100}]},
        {'name': 'Датчик влажности - Кухня (RH_3)', 'serial_number': 'HUM-002',
         'device_type': type_map['Датчик влажности'], 'location_name': 'Кухня',
         'metadata': {'csv_column': 'RH_3', 'period_days': 30},
         'metrics': [{'metric_type': 'humidity', 'name': 'Влажность', 'unit': '%', 'min_value': 0, 'max_value': 100}]},
        {'name': 'Датчик давления', 'serial_number': 'PRES-001',
         'device_type': type_map['Датчик давления'], 'location_name': 'Основной',
         'metadata': {'csv_column': 'Press_mm_hg', 'period_days': 30},
         'metrics': [{'metric_type': 'custom', 'name': 'Давление', 'unit': 'мм рт.ст.', 'min_value': 700, 'max_value': 800}]},
        {'name': 'Умная розетка - Период 1', 'serial_number': 'PLUG-001',
         'device_type': type_map['Умная розетка'], 'location_name': 'Жилая комната',
         'metadata': {'csv_column': 'Appliances', 'period_days': 30, 'period_number': 1},
         'metrics': [{'metric_type': 'power', 'name': 'Энергопотребление', 'unit': 'Wh', 'min_value': 0, 'max_value': 2000}]},
        {'name': 'Умная розетка - Период 2', 'serial_number': 'PLUG-002',
         'device_type': type_map['Умная розетка'], 'location_name': 'Спальня',
         'metadata': {'csv_column': 'Appliances', 'period_days': 30, 'period_number': 2},
         'metrics': [{'metric_type': 'power', 'name': 'Энергопотребление', 'unit': 'Wh', 'min_value': 0, 'max_value': 2000}]},
        {'name': 'Умная розетка - Период 3', 'serial_number': 'PLUG-003',
         'device_type': type_map['Умная розетка'], 'location_name': 'Кухня',
         'metadata': {'csv_column': 'Appliances', 'period_days': 30, 'period_number': 3},
         'metrics': [{'metric_type': 'power', 'name': 'Энергопотребление', 'unit': 'Wh', 'min_value': 0, 'max_value': 2000}]},
        {'name': 'LED лампа - Гостиная', 'serial_number': 'LED-001',
         'device_type': type_map['LED лампа'], 'location_name': 'Гостиная',
         'metadata': {'csv_column': 'lights', 'period_days': 30},
         'metrics': [{'metric_type': 'custom', 'name': 'Освещенность', 'unit': 'Wh', 'min_value': 0, 'max_value': 800}]},
    ]

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

    print("✅ Создано 10 устройств с метриками")
    return True


def create_extra_users_and_devices():
    """Создаёт 3 дополнительных пользователя с 5 устройствами каждый."""

    all_new_serials = [
        d['serial_number']
        for u in USERS_CONFIG
        for d in u['devices']
    ]
    existing = Device.objects.filter(serial_number__in=all_new_serials).count()
    if existing == len(all_new_serials):
        print("✅ Все устройства новых пользователей уже созданы ({} шт.)".format(existing))
        return False

    print("👥 Создаю 3 новых пользователей и их устройства...")

    type_map = get_or_create_device_type_map()

    for user_cfg in USERS_CONFIG:
        # Создаём пользователя
        user, created = User.objects.get_or_create(
            username=user_cfg['username'],
            defaults={
                'email': user_cfg['email'],
                'first_name': user_cfg['first_name'],
                'last_name': user_cfg['last_name'],
            }
        )
        if created:
            user.set_password(user_cfg['password'])
            user.save()
            print(f"  ✅ Пользователь создан: {user_cfg['username']} / {user_cfg['password']}")
        else:
            print(f"  ↩️  Пользователь уже есть: {user_cfg['username']}")

        # Роль
        UserRole.objects.get_or_create(user=user, defaults={'role': user_cfg['role']})

        # Профиль
        UserProfile.objects.get_or_create(user=user)

        # Устройства
        for dev_cfg in user_cfg['devices']:
            metrics_data = dev_cfg['metrics']
            device_type = type_map[dev_cfg['type']]

            device, _ = Device.objects.get_or_create(
                serial_number=dev_cfg['serial_number'],
                defaults={
                    'name': dev_cfg['name'],
                    'device_type': device_type,
                    'location_name': dev_cfg.get('location_name', ''),
                    'metadata': {'csv_column': dev_cfg['csv_column']},
                    'owner': user,
                    'status': 'active',
                    'is_active': True,
                    'installation_date': timezone.now(),
                }
            )
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

    print("✅ Устройства новых пользователей созданы")
    return True


def load_telemetry_for_devices(df, serial_numbers, period_offset_days=0):
    """Загружает телеметрию для списка устройств по их csv_column и периоду."""

    new_records = 0
    period_start = CSV_START + timedelta(days=period_offset_days)
    period_end = period_start + timedelta(days=29)

    for serial in serial_numbers:
        try:
            device = Device.objects.get(serial_number=serial)
        except Device.DoesNotExist:
            continue

        # Пропускаем если телеметрия уже есть для этого устройства
        if Telemetry.objects.filter(device=device).exists():
            continue

        csv_column = device.metadata.get('csv_column')
        if not csv_column or csv_column not in df.columns:
            continue

        # Для PLUG используем номер периода из metadata
        period_number = device.metadata.get('period_number', 1)
        actual_start = CSV_START + timedelta(days=(period_number - 1) * 30 + period_offset_days)
        actual_end = actual_start + timedelta(days=29)

        period_data = df[(df['date'] >= actual_start) & (df['date'] <= actual_end)].copy()
        if period_data.empty:
            # Фолбэк на стандартный период
            period_data = df[(df['date'] >= period_start) & (df['date'] <= period_end)].copy()

        if period_data.empty:
            continue

        daily_avg = period_data.groupby(period_data['date'].dt.date)[csv_column].agg(['mean', 'std', 'count'])

        metric = device.metrics.first()
        if not metric:
            continue

        telemetries = []
        for day, row in daily_avg.iterrows():
            try:
                naive_dt = datetime.combine(day, datetime.min.time().replace(hour=12, minute=0))
                recorded_at = naive_dt.replace(tzinfo=dt_timezone.utc)
                value = float(row['mean'])
                std_val = float(row['std']) if not pd.isna(row['std']) else 0
                count_val = int(row['count']) if not pd.isna(row['count']) else 0

                telemetries.append(Telemetry(
                    device=device,
                    metric=metric,
                    value=value,
                    unit=metric.unit,
                    status='ok',
                    recorded_at=recorded_at,
                    raw_data={'std': std_val, 'count': count_val, 'csv_column': csv_column}
                ))
            except Exception:
                continue

        if telemetries:
            Telemetry.objects.bulk_create(telemetries, batch_size=1000)
            new_records += len(telemetries)

    return new_records


def load_telemetry_data():
    """Загружает телеметрию для всех устройств из CSV."""

    csv_file = 'datasets/energydata_complete.csv'
    if not os.path.exists(csv_file):
        # Фолбэк на старый путь (корень), если датасет ещё не перенесён
        if os.path.exists('energydata_complete.csv'):
            csv_file = 'energydata_complete.csv'
    if not os.path.exists(csv_file):
        print(f"⚠️  Файл {csv_file} не найден, пропускаю загрузку телеметрии")
        return False

    # Быстрая проверка: если телеметрия есть для всех 25 устройств — пропускаем
    all_serials = ADMIN_SERIALS + [d['serial_number'] for u in USERS_CONFIG for d in u['devices']]
    devices_with_telemetry = (
        Telemetry.objects.filter(device__serial_number__in=all_serials)
        .values('device__serial_number').distinct().count()
    )
    if devices_with_telemetry >= len(all_serials):
        print(f"✅ Телеметрия уже загружена ({Telemetry.objects.count()} записей)")
        return False

    print(f"📊 Загружаю телеметрические данные из {csv_file}...")
    df = pd.read_csv(csv_file)
    df['date'] = pd.to_datetime(df['date'])

    total = 0

    # Телеметрия для устройств админа (период 0, т.е. дни 1-30)
    total += load_telemetry_for_devices(df, ADMIN_SERIALS, period_offset_days=0)

    # Телеметрия для новых пользователей — каждый на своём периоде
    for user_cfg in USERS_CONFIG:
        serials = [d['serial_number'] for d in user_cfg['devices']]
        total += load_telemetry_for_devices(df, serials, period_offset_days=user_cfg['period_offset_days'])

    print(f"✅ Телеметрия загружена ({Telemetry.objects.count()} записей)")
    return True


def fix_device_owners():
    """Исправляет owner для устройств пользователей — на случай если они были созданы с owner=admin."""
    fixed = 0
    for user_cfg in USERS_CONFIG:
        user = User.objects.filter(username=user_cfg['username']).first()
        if not user:
            continue
        for dev_cfg in user_cfg['devices']:
            updated = Device.objects.filter(
                serial_number=dev_cfg['serial_number']
            ).exclude(owner=user).update(owner=user)
            fixed += updated
    if fixed:
        print(f"🔧 Исправлен owner для {fixed} устройств")
    else:
        print("✅ Owner у всех устройств корректный")


def main():
    print("\n=== ИНИЦИАЛИЗАЦИЯ БД ===\n")
    create_device_types_and_devices()
    create_extra_users_and_devices()
    fix_device_owners()
    load_telemetry_data()
    print("\n✅ Инициализация завершена!\n")


if __name__ == '__main__':
    main()
