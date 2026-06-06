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

print(f"✅ Создано алертов: {created_count}")
