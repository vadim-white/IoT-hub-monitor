"""Сравнение методов прогнозирования через rolling-origin backtest.

Оценивает точность прогноза (MAE/RMSE/sMAPE) по горизонтам на исторических данных.
Только метрики в консоль, Alert не пишет — научный этап (как detect_anomalies).

Примеры:
    python manage.py forecast_telemetry --device TEMP-001 --metric temperature --method naive
    python manage.py forecast_telemetry --device TEMP-001 --metric temperature --method holtwinters --horizon 36
"""
import json

from django.core.management.base import BaseCommand

from iot_hub.apps.devices.models import Device
from iot_hub.apps.telemetry.ml.loader import load_series
from iot_hub.apps.telemetry.ml.forecasters import build_forecaster
from iot_hub.apps.telemetry.ml.forecast_evaluation import rolling_origin_backtest


class Command(BaseCommand):
    help = "Сравнение методов прогнозирования (rolling-origin backtest)"

    def add_arguments(self, parser):
        parser.add_argument("--device", default=None)
        parser.add_argument("--metric", default=None)
        parser.add_argument("--method", default="naive",
                            help="naive, holtwinters, lstm")
        parser.add_argument("--horizon", type=int, default=36,
                            help="горизонт прогноза в точках (36 = 6ч при шаге 10мин)")
        parser.add_argument("--seasonal-periods", type=int, default=144,
                            help="период сезонности (144 = сутки)")
        parser.add_argument("--initial-train", type=int, default=2880,
                            help="минимум истории для первого fit (2880 = 20 дней)")
        parser.add_argument("--step", type=int, default=144,
                            help="сдвиг origin между итерациями backtest")
        parser.add_argument("--max-origins", type=int, default=10)
        parser.add_argument("--report", choices=["text", "json"], default="text")
        parser.add_argument("--random-state", type=int, default=42)
        # lstm-специфичные
        parser.add_argument("--window", type=int, default=144)
        parser.add_argument("--epochs", type=int, default=100)
        parser.add_argument("--lr", type=float, default=1e-3)
        parser.add_argument("--hidden", type=int, default=32)

    def handle(self, *args, **opts):
        qs = Device.objects.prefetch_related("metrics")
        if opts["device"]:
            qs = qs.filter(serial_number=opts["device"])
        devices = list(qs)
        if not devices:
            self.stderr.write(self.style.ERROR("Устройства не найдены"))
            return

        results = []
        for device in devices:
            metrics = device.metrics.all()
            if opts["metric"]:
                metrics = [m for m in metrics if m.metric_type == opts["metric"]]
            for metric in metrics:
                series = load_series(device, metric)
                if len(series) < opts["initial_train"] + opts["horizon"]:
                    continue

                factory = lambda: build_forecaster(
                    opts["method"], **self._method_params(opts))
                res = rolling_origin_backtest(
                    factory, series, horizon=opts["horizon"],
                    initial_train=opts["initial_train"], step=opts["step"],
                    max_origins=opts["max_origins"])
                if res["n_origins"]:
                    results.append((device, metric, res))

        if not results:
            self.stderr.write(self.style.ERROR("Нет рядов достаточной длины"))
            return

        if opts["report"] == "json":
            self._report_json(results, opts)
        else:
            self._report_text(results, opts)

    def _method_params(self, opts) -> dict:
        m = opts["method"]
        if m == "naive":
            return {"seasonal_periods": opts["seasonal_periods"]}
        if m == "holtwinters":
            return {"seasonal_periods": opts["seasonal_periods"]}
        if m == "lstm":
            return {
                "window": opts["window"], "epochs": opts["epochs"],
                "lr": opts["lr"], "hidden": opts["hidden"],
                "random_state": opts["random_state"],
            }
        return {}

    def _report_text(self, results, opts):
        for device, metric, res in results:
            self.stdout.write(
                f"\n{device.serial_number} / {metric.metric_type}  "
                f"(метод={opts['method']}, горизонт={opts['horizon']}, "
                f"origins={res['n_origins']})")
            self.stdout.write(
                f"  MAE={res['mae']:.3f}  RMSE={res['rmse']:.3f}  sMAPE={res['mape']:.1f}%")

    def _report_json(self, results, opts):
        payload = [
            {
                "device": d.serial_number, "metric": m.metric_type,
                "method": opts["method"], "horizon": opts["horizon"],
                "mae": round(r["mae"], 4), "rmse": round(r["rmse"], 4),
                "smape": round(r["mape"], 2), "n_origins": r["n_origins"],
            }
            for d, m, r in results
        ]
        self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
