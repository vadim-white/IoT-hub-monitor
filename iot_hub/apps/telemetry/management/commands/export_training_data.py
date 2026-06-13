"""Выгружает телеметрию с ground-truth метками в CSV для обучения в Colab (Фаза 4, инкр. 2).

Зачем отдельная команда, а не export_telemetry_csv: тот HTTP-ориентирован
(HttpResponse) и НЕ содержит ground-truth меток. Для обучения и evaluation в Colab
метки обязательны — берём их из Telemetry.raw_data['anomaly'] (как loader.load_series).

CSV-формат параллелен loader.load_series (loader.py:32-37) и dataset_csv.load_series_from_csv:
колонки device,metric,value,recorded_at,is_anomaly,anomaly_type, сортировка по
(device, metric, recorded_at). recorded_at пишется БЕЗ tz (как load_series делает
.replace(tzinfo=None)) — чтобы TimeSeries из CSV был байт-в-байт как из БД.

Пример:
    python manage.py export_training_data --device TEMP-001 --metric temperature \
        --output /tmp/train.csv
"""
import csv

from django.core.management.base import BaseCommand
from django.utils import timezone

from iot_hub.apps.devices.models import Device
from iot_hub.apps.telemetry.models import Telemetry

CSV_COLUMNS = ["device", "metric", "value", "recorded_at", "is_anomaly", "anomaly_type"]


class Command(BaseCommand):
    help = "Выгрузить телеметрию с метками в CSV для обучения моделей в Colab"

    def add_arguments(self, parser):
        parser.add_argument("--device", default=None,
                            help="serial_number (по умолчанию — все)")
        parser.add_argument("--metric", default=None,
                            help="metric_type (по умолчанию — все метрики)")
        parser.add_argument("--days", type=int, default=None,
                            help="окно в днях (по умолчанию — вся история)")
        parser.add_argument("--output", default="training_data.csv",
                            help="путь к CSV (по умолчанию training_data.csv)")

    def handle(self, *args, **opts):
        qs = Telemetry.objects.select_related("device", "metric")
        if opts["device"]:
            qs = qs.filter(device__serial_number=opts["device"])
        if opts["metric"]:
            qs = qs.filter(metric__metric_type=opts["metric"])
        if opts["days"]:
            cutoff = timezone.now() - timezone.timedelta(days=opts["days"])
            qs = qs.filter(recorded_at__gte=cutoff)
        # хронология внутри ряда обязательна для TimeSeries (rolling требует возрастания)
        qs = qs.order_by("device__serial_number", "metric__metric_type", "recorded_at")

        rows = qs.values_list(
            "device__serial_number", "metric__metric_type",
            "value", "recorded_at", "raw_data",
        )

        written = 0
        with open(opts["output"], "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
            for serial, metric_type, value, recorded_at, raw_data in rows.iterator():
                anomaly = (raw_data or {}).get("anomaly", {})
                is_anomaly = bool(anomaly.get("is_anomaly", False))
                anomaly_type = anomaly.get("type", "") if is_anomaly else ""
                writer.writerow([
                    serial, metric_type, value,
                    recorded_at.replace(tzinfo=None).isoformat(),
                    is_anomaly, anomaly_type,
                ])
                written += 1

        if not written:
            self.stderr.write(self.style.WARNING("Нет телеметрии под заданные фильтры"))
            return
        self.stdout.write(self.style.SUCCESS(
            f"Записано строк: {written} → {opts['output']}"))
