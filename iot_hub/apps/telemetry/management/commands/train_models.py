"""Обучает ML-модель на телеметрии и сохраняет веса в ml/models/ (Фаза 4).

В отличие от detect_anomalies/forecast_telemetry (которые обучают на лету и
выбрасывают модель), эта команда производит ПЕРСИСТЕНТНЫЙ артефакт: обученные
веса + JSON-манифест. Потом detect_anomalies --use-cache грузит их вместо
переобучения. Артефакт — то, что предъявляется на защите как «обученная модель».

Примеры:
    python manage.py train_models --device TEMP-001 --metric temperature --method autoencoder
    python manage.py train_models --method iforest               # все устройства/метрики
    python manage.py train_models --kind forecaster --method holtwinters
"""
import time

from django.core.management.base import BaseCommand

from iot_hub.apps.devices.models import Device
from iot_hub.apps.telemetry.ml.cli_params import detector_params, forecaster_params
from iot_hub.apps.telemetry.ml.detectors import build_detector
from iot_hub.apps.telemetry.ml.forecasters import build_forecaster
from iot_hub.apps.telemetry.ml.loader import load_series
from iot_hub.apps.telemetry.ml.persistence import model_key


class Command(BaseCommand):
    help = "Обучить ML-модель и сохранить веса в ml/models/"

    def add_arguments(self, parser):
        parser.add_argument("--device", default=None,
                            help="serial_number (по умолчанию — все)")
        parser.add_argument("--metric", default=None,
                            help="metric_type (по умолчанию — все метрики устройства)")
        parser.add_argument("--kind", choices=["detector", "forecaster"],
                            default="detector", help="что обучаем")
        parser.add_argument("--method", default="iforest",
                            help="detector: zscore/iforest/autoencoder; "
                                 "forecaster: naive/holtwinters/lstm")
        # гиперпараметры (совпадают по именам с detect_anomalies/forecast_telemetry,
        # чтобы sha кэша совпадал при последующем --use-cache)
        parser.add_argument("--window", type=int, default=24)
        parser.add_argument("--threshold", type=float, default=3.0)
        parser.add_argument("--days", type=int, default=None)
        parser.add_argument("--contamination", type=float, default=0.02)
        parser.add_argument("--n-estimators", type=int, default=200)
        parser.add_argument("--random-state", type=int, default=42)
        parser.add_argument("--epochs", type=int, default=150)
        parser.add_argument("--latent-dim", type=int, default=8)
        parser.add_argument("--lr", type=float, default=1e-3)
        parser.add_argument("--threshold-percentile", type=float, default=98.0)
        parser.add_argument("--seasonal-periods", type=int, default=144)
        parser.add_argument("--hidden", type=int, default=32)

    def handle(self, *args, **opts):
        qs = Device.objects.prefetch_related("metrics")
        if opts["device"]:
            qs = qs.filter(serial_number=opts["device"])
        devices = list(qs)
        if not devices:
            self.stderr.write(self.style.ERROR("Устройства не найдены"))
            return

        is_detector = opts["kind"] == "detector"
        method = opts["method"]
        trained = 0
        for device in devices:
            metrics = device.metrics.all()
            if opts["metric"]:
                metrics = [m for m in metrics if m.metric_type == opts["metric"]]
            for metric in metrics:
                series = load_series(device, metric, days=opts["days"]) if is_detector \
                    else load_series(device, metric)
                if len(series) <= opts["window"]:
                    continue

                if is_detector:
                    model = build_detector(method, **detector_params(method, opts))
                else:
                    model = build_forecaster(method, **forecaster_params(method, opts))

                t0 = time.perf_counter()
                model.fit(series)
                elapsed = time.perf_counter() - t0

                stem = model_key(model.name, device.serial_number, metric.metric_type)
                model.save(stem)
                trained += 1
                self.stdout.write(
                    f"  {device.serial_number}/{metric.metric_type}: "
                    f"{model.name} обучен за {elapsed:.2f}с → {stem.name}")

        if not trained:
            self.stderr.write(self.style.ERROR("Нет рядов длиннее окна для обучения"))
            return
        self.stdout.write(self.style.SUCCESS(f"\nОбучено и сохранено моделей: {trained}"))
