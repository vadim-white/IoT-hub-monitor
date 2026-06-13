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
from django.utils import timezone

from iot_hub.apps.devices.models import Device
from iot_hub.apps.telemetry.ml.detectors import build_detector
from iot_hub.apps.telemetry.ml.cli_params import detector_params
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
                            help="метод детекции из реестра: zscore, iforest, autoencoder")
        parser.add_argument("--window", type=int, default=24,
                            help="размер окна в точках (24 = 4ч при шаге 10 мин)")
        parser.add_argument("--threshold", type=float, default=3.0,
                            help="порог решения по anomaly score (для iforest 0.0 ≈ sklearn-predict)")
        parser.add_argument("--days", type=int, default=None,
                            help="ограничить выборку последними N днями")
        parser.add_argument("--report", choices=["text", "json"], default="text")
        # запись ML-аномалий в Alert (по умолчанию команда только оценивает)
        parser.add_argument("--write-alerts", action="store_true",
                            help="создавать Alert(source=ml_anomaly) по аномалиям в свежем хвосте ряда")
        parser.add_argument("--tail", type=int, default=144,
                            help="--write-alerts: сколько последних точек считать «свежими» (144 = сутки)")
        parser.add_argument("--dedup-hours", type=int, default=6,
                            help="--write-alerts: окно дедупликации алертов того же типа (часы)")
        parser.add_argument("--alert-severity", default="warning",
                            choices=["info", "warning", "critical"],
                            help="--write-alerts: severity создаваемых ML-алертов")
        # параметры Isolation Forest (игнорируются другими методами)
        parser.add_argument("--contamination", type=float, default=0.02,
                            help="iforest: ожидаемая доля аномалий")
        parser.add_argument("--n-estimators", type=int, default=200,
                            help="iforest: число деревьев")
        parser.add_argument("--random-state", type=int, default=42,
                            help="iforest/autoencoder: seed для воспроизводимости")
        # параметры автоэнкодера (игнорируются другими методами)
        parser.add_argument("--epochs", type=int, default=150,
                            help="autoencoder: число эпох обучения")
        parser.add_argument("--latent-dim", type=int, default=8,
                            help="autoencoder: размер скрытого слоя (bottleneck)")
        parser.add_argument("--lr", type=float, default=1e-3,
                            help="autoencoder: learning rate")
        parser.add_argument("--threshold-percentile", type=float, default=98.0,
                            help="autoencoder: перцентиль ошибки реконструкции для порога")
        # кэш весов (Фаза 4): грузить обученную модель вместо переобучения
        parser.add_argument("--use-cache", action="store_true",
                            help="загрузить веса из ml/models/ (при miss/несовпадении — fit)")
        parser.add_argument("--save-cache", action="store_true",
                            help="--use-cache: пересохранить веса после обучения на miss")

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
        alerts_created = 0
        for device in devices:
            metrics = device.metrics.all()
            if opts["metric"]:
                metrics = [m for m in metrics if m.metric_type == opts["metric"]]
            for metric in metrics:
                series = load_series(device, metric, days=opts["days"])
                if len(series) <= opts["window"]:
                    continue

                params = detector_params(opts["method"], opts)
                detector = build_detector(opts["method"], **params)
                detector = self._fit_or_load(detector, series, device, metric, opts)
                result = detector.predict(series)

                pm = point_metrics(series.labels, result.predictions, result.warmup_mask)
                ptr = per_type_recall(series, result.predictions, result.warmup_mask)
                lat = detection_latency(series, result.predictions, result.warmup_mask)

                for k in agg:
                    agg[k] += getattr(pm, k)
                results.append((device, metric, pm, ptr, lat, result.meta))

                if opts["write_alerts"]:
                    alerts_created += self._write_alerts(
                        device, metric, series, result, opts)

        if not results:
            self.stderr.write(self.style.ERROR("Нет рядов длиннее окна для анализа"))
            return

        if opts["write_alerts"]:
            self.stdout.write(self.style.SUCCESS(
                f"\nСоздано ML-алертов: {alerts_created}"))

        if opts["report"] == "json":
            self._report_json(results, agg)
        else:
            self._report_text(results, agg)

    def _fit_or_load(self, detector, series, device, metric, opts):
        """С --use-cache грузит веса из ml/models/; при miss/несовпадении — fit.

        Без флага поведение прежнее (всегда fit). Возвращает готовый детектор.
        """
        if not opts["use_cache"]:
            return detector.fit(series)

        from iot_hub.apps.telemetry.ml.persistence import (
            CacheMismatchError, model_key,
        )

        stem = model_key(detector.name, device.serial_number, metric.metric_type)
        try:
            detector.load(stem)
            self.stdout.write(self.style.SUCCESS(f"  [cache] загружено: {stem.name}"))
            return detector
        except (FileNotFoundError, CacheMismatchError) as e:
            self.stdout.write(f"  [cache] miss ({type(e).__name__}) → обучение")
            detector.fit(series)
            if opts["save_cache"]:
                detector.save(stem)
                self.stdout.write(f"  [cache] сохранено: {stem.name}")
            return detector

    def _write_alerts(self, device, metric, series, result, opts):
        """Создаёт ML-алерт по самой сильной аномалии в свежем хвосте ряда.

        Смотрим только последние --tail точек (имитация скоринга свежих данных),
        исключаем warmup, берём точку с максимальным score. Дедуп — в create_ml_alert.
        Возвращает число созданных алертов (0 или 1).
        """
        from datetime import datetime

        import numpy as np

        from iot_hub.apps.alerts.application.ml_alerts import create_ml_alert
        from iot_hub.apps.telemetry.models import Telemetry

        n = len(series)
        tail = min(opts["tail"], n)
        start = n - tail
        # кандидаты: аномалия, вне warmup, в пределах хвоста
        mask = result.predictions & ~result.warmup_mask
        mask[:start] = False
        idx = np.flatnonzero(mask)
        if idx.size == 0:
            return 0

        best = idx[int(np.argmax(result.scores[idx]))]
        value = float(series.values[best])
        score = float(result.scores[best])
        # связываем точку с её Telemetry-записью по времени (best-effort)
        ts = series.timestamps[best].astype("datetime64[us]").astype(datetime)
        telemetry = Telemetry.objects.filter(
            device=device, metric=metric,
            recorded_at=ts.replace(tzinfo=timezone.utc),
        ).first()

        _, created = create_ml_alert(
            device=device, metric=metric, source="ml_anomaly",
            severity=opts["alert_severity"], value=value, message=(
                f"ML-аномалия ({result.meta['method']}): {metric.name} = "
                f"{value:.2f} {metric.unit} (anomaly score {score:.2f})"),
            telemetry=telemetry, dedup_hours=opts["dedup_hours"],
            metadata={
                "method": result.meta["method"],
                "score": round(score, 4),
                "window": result.meta.get("window"),
                "threshold": result.threshold,
            },
        )
        return 1 if created else 0

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
