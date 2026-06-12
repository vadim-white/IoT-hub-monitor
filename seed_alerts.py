"""
Создаёт демо-алерты для всех пользователей.
Запускать: python seed_alerts.py
"""
import os
import sys
import django
import random
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iot_hub.config.settings')
django.setup()

from django.utils import timezone
from django.contrib.auth.models import User
from iot_hub.apps.devices.models import Device, DeviceMetric, AlertThreshold
from iot_hub.apps.alerts.models import Alert

# --reset: удалить все алерты и пересоздать
if '--reset' in sys.argv:
    deleted, _ = Alert.objects.all().delete()
    print(f"🗑️  Удалено алертов: {deleted}")
elif Alert.objects.exists():
    print("✅ Алерты уже существуют, пропуск.")
    sys.exit(0)

now = timezone.now()

# Шаблоны алертов по типу метрики
ALERT_TEMPLATES = {
    'temperature': [
        {'severity': 'warning',  'delta': +3.5,  'msg': 'Температура превысила норму: {value:.1f}°C (порог +{limit}°C)'},
        {'severity': 'critical', 'delta': +7.2,  'msg': 'Критически высокая температура: {value:.1f}°C'},
        {'severity': 'warning',  'delta': -4.0,  'msg': 'Температура ниже нормы: {value:.1f}°C'},
        {'severity': 'info',     'delta': +1.8,  'msg': 'Температура приближается к верхнему порогу: {value:.1f}°C'},
    ],
    'humidity': [
        {'severity': 'warning',  'delta': +15.0, 'msg': 'Высокая влажность: {value:.1f}% (норма до 70%)'},
        {'severity': 'critical', 'delta': +25.0, 'msg': 'Критический уровень влажности: {value:.1f}%'},
        {'severity': 'warning',  'delta': -20.0, 'msg': 'Слишком низкая влажность: {value:.1f}%'},
    ],
    'custom': [
        {'severity': 'warning',  'delta': +15.0, 'msg': 'Значение вышло за пределы нормы: {value:.1f}'},
        {'severity': 'info',     'delta': +8.0,  'msg': 'Показатель приближается к порогу: {value:.1f}'},
    ],
    'power': [
        {'severity': 'warning',  'delta': +200.0,'msg': 'Повышенное энергопотребление: {value:.0f} Wh'},
        {'severity': 'critical', 'delta': +500.0,'msg': 'Критическое энергопотребление: {value:.0f} Wh'},
    ],
    'default': [
        {'severity': 'warning',  'delta': +10.0, 'msg': 'Значение вышло за пределы: {value:.1f}'},
        {'severity': 'info',     'delta': +5.0,  'msg': 'Незначительное отклонение: {value:.1f}'},
    ],
}

STATUS_WEIGHTS = ['new', 'new', 'acknowledged', 'resolved', 'closed']

created_count = 0

for user in User.objects.all():
    devices = Device.objects.filter(owner=user).prefetch_related('metrics')
    if not devices.exists():
        continue

    # Берём 2-3 случайных устройства пользователя
    sample_devices = random.sample(list(devices), min(len(list(devices)), random.randint(2, 3)))

    for device in sample_devices:
        metrics = list(device.metrics.filter(is_active=True))
        if not metrics:
            continue

        # Берём 1-2 метрики
        sample_metrics = random.sample(metrics, min(len(metrics), random.randint(1, 2)))

        for metric in sample_metrics:
            templates = ALERT_TEMPLATES.get(metric.metric_type, ALERT_TEMPLATES['default'])
            # 1-2 алерта на метрику
            for tpl in random.sample(templates, min(len(templates), random.randint(1, 2))):
                base = (metric.max_value or 50) if tpl['delta'] > 0 else (metric.min_value or 0)
                value = base + tpl['delta'] * random.uniform(0.8, 1.3)
                limit = abs(tpl['delta'])

                # Порог (create or get)
                threshold, _ = AlertThreshold.objects.get_or_create(
                    metric=metric,
                    severity=tpl['severity'],
                    defaults={
                        'upper_bound': base + limit if tpl['delta'] > 0 else None,
                        'lower_bound': base - limit if tpl['delta'] < 0 else None,
                        'is_active': True,
                    }
                )

                status = random.choice(STATUS_WEIGHTS)
                created_at = now - timedelta(
                    days=random.randint(0, 14),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59)
                )

                alert = Alert(
                    device=device,
                    metric=metric,
                    threshold=threshold,
                    telemetry=None,
                    severity=tpl['severity'],
                    status=status,
                    message=tpl['msg'].format(value=value, limit=round(limit, 1)),
                    value=round(value, 2),
                    created_at=created_at,
                    updated_at=created_at,
                )

                if status == 'acknowledged':
                    alert.acknowledged_at = created_at + timedelta(hours=random.randint(1, 6))
                    alert.acknowledged_by = user
                elif status in ('resolved', 'closed'):
                    alert.acknowledged_at = created_at + timedelta(hours=random.randint(1, 3))
                    alert.acknowledged_by = user
                    alert.resolved_at = created_at + timedelta(hours=random.randint(4, 12))
                    alert.resolved_by = user

                alert.save()
                created_count += 1

print(f"✅ Создано пороговых алертов: {created_count}")


# ── Демо ML-алертов (заглушка витрины ML на деплое) ───────────────────────────
# Это НЕ результат прогона моделей, а статичные демо-записи, чтобы на Render была
# видна ML-секция (бейджи source=ml_anomaly/ml_forecast + фильтр в /alerts/).
# Реальные ML-алерты создаёт `manage.py detect_anomalies/forecast_telemetry
# --write-alerts` по живой телеметрии. Когда подключим сохранение весов/ONNX и
# автоскоринг — этот демо-блок убираем, а команды зовём из entrypoint вместо него.
ML_DEMO = [
    {
        'source': 'ml_anomaly', 'severity': 'warning', 'metric_type': 'temperature',
        'msg': 'ML-аномалия (iforest): Температура = 36.13 °C (anomaly score 0.61)',
        'value': 36.13,
        'metadata': {'method': 'iforest', 'score': 0.61, 'window': 24, 'threshold': 0.0},
    },
    {
        'source': 'ml_anomaly', 'severity': 'warning', 'metric_type': 'humidity',
        'msg': 'ML-аномалия (iforest): Влажность = 12.40 % (anomaly score 0.48)',
        'value': 12.40,
        'metadata': {'method': 'iforest', 'score': 0.48, 'window': 24, 'threshold': 0.0},
    },
    {
        'source': 'ml_forecast', 'severity': 'critical', 'metric_type': 'temperature',
        'msg': 'Предиктивный алерт (holtwinters): Температура выйдет выше порога '
               '57.2 °C через ~5.0 ч (прогноз 58.40)',
        'value': 58.40,
        'metadata': {'method': 'holtwinters', 'lead_time_hours': 5.0,
                     'forecast_value': 58.4, 'bound': 57.2, 'bound_kind': 'выше',
                     'horizon': 36},
    },
]

ml_count = 0
for user in User.objects.all():
    devices = list(Device.objects.filter(owner=user).prefetch_related('metrics'))
    for demo in ML_DEMO:
        # ищем устройство с подходящей метрикой
        target = next(
            ((d, m) for d in devices for m in d.metrics.filter(is_active=True)
             if m.metric_type == demo['metric_type']),
            None)
        if target is None:
            continue
        device, metric = target
        created_at = now - timedelta(hours=random.randint(1, 36))
        Alert.objects.create(
            device=device, metric=metric, threshold=None, telemetry=None,
            source=demo['source'], severity=demo['severity'], status='new',
            message=demo['msg'], value=demo['value'], metadata=demo['metadata'],
            created_at=created_at, updated_at=created_at,
        )
        ml_count += 1

print(f"✅ Создано демо ML-алертов: {ml_count}")
print(f"✅ Всего алертов: {created_count + ml_count}")
