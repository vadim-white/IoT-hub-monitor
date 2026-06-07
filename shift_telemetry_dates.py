"""
Сдвигает даты телеметрии каждого устройства индивидуально,
чтобы его последняя запись всегда была сегодня.

Алгоритм для каждого устройства:
  offset = today - max(recorded_at для этого устройства).date()
  UPDATE ... WHERE device_id = X

Время суток не меняется. Идемпотентен: если max_date устройства
уже равна сегодня — пропускает его.
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iot_hub.config.settings')
django.setup()

from django.utils import timezone
from django.db import connection
from django.db.models import Max
from iot_hub.apps.telemetry.models import Telemetry


def shift_telemetry_dates():
    if not Telemetry.objects.exists():
        print("⏭️  Телеметрия пуста — сдвиг не нужен")
        return

    today = timezone.now().date()

    # Получаем max recorded_at по каждому устройству одним запросом
    device_max_dates = (
        Telemetry.objects
        .values('device_id')
        .annotate(max_date=Max('recorded_at'))
    )

    total_updated = 0
    skipped = 0

    with connection.cursor() as cursor:
        for row in device_max_dates:
            device_id = row['device_id']
            max_date = row['max_date'].date()

            if max_date == today:
                skipped += 1
                continue

            offset_days = (today - max_date).days
            cursor.execute(
                "UPDATE telemetry_telemetry SET recorded_at = recorded_at + %s::interval WHERE device_id = %s",
                [f"{offset_days} days", str(device_id)]
            )
            total_updated += cursor.rowcount

    if total_updated == 0:
        print(f"✅ Даты телеметрии актуальны у всех устройств (последняя запись: {today})")
    else:
        print(f"📅 Сдвинуто {total_updated} записей для {total_updated} устройств → все заканчиваются {today}")
        if skipped:
            print(f"   ↩️  Пропущено {skipped} устройств (уже актуальны)")


if __name__ == '__main__':
    shift_telemetry_dates()