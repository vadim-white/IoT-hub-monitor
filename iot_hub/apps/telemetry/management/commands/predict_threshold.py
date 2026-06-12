"""Предиктивный алерт: обучает прогноз на истории метрики и говорит, когда (если)
прогноз пересечёт порог AlertThreshold. Только печать вердикта, Alert не пишет.

Примеры:
    python manage.py predict_threshold --device TEMP-003 --metric temperature --method holtwinters
    python manage.py predict_threshold --device TEMP-003 --metric temperature --upper-bound 40
"""
import numpy as np
from django.core.management.base import BaseCommand

from iot_hub.apps.devices.models import Device, AlertThreshold
from iot_hub.apps.telemetry.ml.loader import load_series
from iot_hub.apps.telemetry.ml.forecasters import build_forecaster
from iot_hub.apps.telemetry.ml.forecast_base import infer_step
from iot_hub.apps.telemetry.ml.predictive_alert import predict_threshold_crossing


class Command(BaseCommand):
    help = "Предиктивный алерт: когда прогноз метрики выйдет за порог"

    def add_arguments(self, parser):
        parser.add_argument("--device", required=True)
        parser.add_argument("--metric", required=True)
        parser.add_argument("--method", default="naive", help="naive, holtwinters, lstm")
        parser.add_argument("--horizon", type=int, default=36)
        parser.add_argument("--seasonal-periods", type=int, default=144)
        parser.add_argument("--use-interval", action="store_true",
                            help="алертить по границе интервала (раньше, консервативнее)")
        # fallback-границы, если у метрики нет активного AlertThreshold в БД
        parser.add_argument("--upper-bound", type=float, default=None)
        parser.add_argument("--lower-bound", type=float, default=None)

    def handle(self, *args, **opts):
        device = Device.objects.filter(serial_number=opts["device"]).first()
        if not device:
            self.stderr.write(self.style.ERROR("Устройство не найдено"))
            return
        metric = device.metrics.filter(metric_type=opts["metric"]).first()
        if not metric:
            self.stderr.write(self.style.ERROR("Метрика не найдена"))
            return

        lower, upper = self._resolve_bounds(metric, opts)
        if lower is None and upper is None:
            self.stderr.write(self.style.ERROR(
                "Нет порогов: задайте AlertThreshold или --upper-bound/--lower-bound"))
            return

        series = load_series(device, metric)
        if len(series) < opts["seasonal_periods"]:
            self.stderr.write(self.style.ERROR("Слишком короткий ряд"))
            return

        params = {"seasonal_periods": opts["seasonal_periods"]} \
            if opts["method"] in ("naive", "holtwinters") else {}
        forecaster = build_forecaster(opts["method"], **params).fit(series)
        fc = forecaster.forecast(opts["horizon"])

        step_min = infer_step(series.timestamps) / np.timedelta64(1, "m")
        crossing = predict_threshold_crossing(
            fc, lower, upper, float(step_min), use_interval=opts["use_interval"])

        self._report(device, metric, crossing, lower, upper, opts)

    def _resolve_bounds(self, metric, opts):
        # явные CLI-границы приоритетнее (для экспериментов/демо); БД — fallback,
        # когда соответствующий флаг не задан
        th = AlertThreshold.objects.filter(metric=metric, is_active=True).first()
        lower = opts["lower_bound"]
        upper = opts["upper_bound"]
        if th:
            if lower is None and th.lower_bound is not None:
                lower = th.lower_bound
            if upper is None and th.upper_bound is not None:
                upper = th.upper_bound
        return lower, upper

    def _report(self, device, metric, c, lower, upper, opts):
        head = f"{device.serial_number} / {metric.metric_type} (метод={opts['method']})"
        if not c.will_cross:
            self.stdout.write(self.style.SUCCESS(
                f"{head}: в пределах горизонта {opts['horizon']} точек порог не пересечён "
                f"(границы: lower={lower}, upper={upper})"))
            return
        bound_val = upper if c.bound_type == "upper" else lower
        ts = np.datetime_as_string(c.crossing_timestamp, unit="m")
        self.stdout.write(self.style.WARNING(
            f"{head}: прогноз пересечёт {c.bound_type}_bound={bound_val} через "
            f"~{c.lead_time_hours:.1f}ч ({c.lead_time_points} точек), значение "
            f"{c.crossing_value:.2f} в {ts} [{c.confidence}]"))
