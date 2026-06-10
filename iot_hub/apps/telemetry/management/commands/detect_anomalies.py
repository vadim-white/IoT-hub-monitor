"""Прогоняет детектор аномалий по телеметрии и оценивает его против ground-truth.

На baseline-этапе команда только ОЦЕНИВАЕТ (метрики в консоль), Alert не пишет —
фокус инкремента на сравнении методов (научная часть диплома). Данные берутся
из БД (синтетические, с метками в raw_data['anomaly']).

Примеры:
    python manage.py detect_anomalies --device TEMP-003 --metric temperature
    python manage.py detect_anomalies --method zscore --window 144 --threshold 3.5
    python manage.py detect_anomalies --report json
"""
import json

from django.core.management.base import BaseCommand

from iot_hub.apps.devices.models import Device
from iot_hub.apps.telemetry.ml.detectors import build_detector
from iot_hub.apps.telemetry.ml.loader import load_series
from iot_hub.apps.telemetry.ml.evaluation import (
    point_metrics, per_type_recall, detection_latency,
)


class Command(BaseCommand):
    help = "Обнаружение аномалий в телеметрии и оценка метрик против ground-truth"

    def add_arguments(self, parser):
        parser.add_argument("--device", default=None,
                            help="serial_number устройства (по умолчанию — все)")
        parser.add_argument("--metric", default=None,
                            help="metric_type (по умолчанию — все метрики устройства)")
        parser.add_argument("--method", default="zscore",
                            help="метод детекции из реестра: zscore, iforest")
        parser.add_argument("--window", type=int, default=24,
                            help="размер окна в точках (24 = 4ч при шаге 10 мин)")
        parser.add_argument("--threshold", type=float, default=3.0,
                            help="порог решения по anomaly score (для iforest 0.0 ≈ sklearn-predict)")
        parser.add_argument("--days", type=int, default=None,
                            help="ограничить выборку последними N днями")
        parser.add_argument("--report", choices=["text", "json"], default="text")
        # параметры Isolation Forest (игнорируются другими методами)
        parser.add_argument("--contamination", type=float, default=0.02,
                            help="iforest: ожидаемая доля аномалий")
        parser.add_argument("--n-estimators", type=int, default=200,
                            help="iforest: число деревьев")
        parser.add_argument("--random-state", type=int, default=42,
                            help="iforest: seed для воспроизводимости")

    def handle(self, *args, **opts):
        qs = Device.objects.prefetch_related("metrics")
        if opts["device"]:
            qs = qs.filter(serial_number=opts["device"])
        devices = list(qs)
        if not devices:
            self.stderr.write(self.style.ERROR("Устройства не найдены"))
            return

        results = []
        agg = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
        for device in devices:
            metrics = device.metrics.all()
            if opts["metric"]:
                metrics = [m for m in metrics if m.metric_type == opts["metric"]]
            for metric in metrics:
                series = load_series(device, metric, days=opts["days"])
                if len(series) <= opts["window"]:
                    continue

                params = {"window": opts["window"], "threshold": opts["threshold"]}
                if opts["method"] == "iforest":
                    params.update(
                        contamination=opts["contamination"],
                        n_estimators=opts["n_estimators"],
                        random_state=opts["random_state"],
                    )
                detector = build_detector(opts["method"], **params)
                result = detector.fit(series).predict(series)

                pm = point_metrics(series.labels, result.predictions, result.warmup_mask)
                ptr = per_type_recall(series, result.predictions, result.warmup_mask)
                lat = detection_latency(series, result.predictions, result.warmup_mask)

                for k in agg:
                    agg[k] += getattr(pm, k)
                results.append((device, metric, pm, ptr, lat, result.meta))

        if not results:
            self.stderr.write(self.style.ERROR("Нет рядов длиннее окна для анализа"))
            return

        if opts["report"] == "json":
            self._report_json(results, agg)
        else:
            self._report_text(results, agg)

    def _report_text(self, results, agg):
        for device, metric, pm, ptr, lat, meta in results:
            self.stdout.write(
                f"\n{device.serial_number} / {metric.metric_type}  "
                f"(оценено={pm.n_evaluated}, аномалий={pm.support_pos})")
            self.stdout.write(
                f"  method={meta['method']} window={meta['window']} "
                f"threshold={meta['params']['threshold']}")
            self.stdout.write(
                f"  precision={pm.precision:.3f} recall={pm.recall:.3f} "
                f"f1={pm.f1:.3f} false_alarm_rate={pm.false_alarm_rate:.4f}")
            self.stdout.write(
                f"  TP={pm.tp} FP={pm.fp} FN={pm.fn} TN={pm.tn}")
            if ptr:
                self.stdout.write("  recall по типам: " +
                                  " ".join(f"{k}={v:.2f}" for k, v in ptr.items()))
            if lat:
                ml = lat["median_latency_points"]
                self.stdout.write(
                    f"  эпизодов={lat['episodes']} обнаружено={lat['detected']} "
                    f"пропущено={lat['missed']} медиана задержки="
                    f"{ml if ml is not None else '—'} точек")

        tp, fp, fn = agg["tp"], agg["fp"], agg["fn"]
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        self.stdout.write(self.style.SUCCESS(
            f"\nИТОГО по всем рядам: precision={prec:.3f} recall={rec:.3f} f1={f1:.3f} "
            f"(TP={tp} FP={fp} FN={fn} TN={agg['tn']})"))

    def _report_json(self, results, agg):
        payload = [
            {
                "device": device.serial_number,
                "metric": metric.metric_type,
                "method": meta["method"],
                "window": meta["window"],
                "threshold": meta["params"]["threshold"],
                "precision": round(pm.precision, 4),
                "recall": round(pm.recall, 4),
                "f1": round(pm.f1, 4),
                "false_alarm_rate": round(pm.false_alarm_rate, 4),
                "support_pos": pm.support_pos,
                "n_evaluated": pm.n_evaluated,
                "per_type_recall": {k: round(v, 4) for k, v in ptr.items()},
                "detection_latency": lat,
            }
            for device, metric, pm, ptr, lat, meta in results
        ]
        self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
