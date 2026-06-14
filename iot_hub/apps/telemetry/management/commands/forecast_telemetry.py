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
from iot_hub.apps.telemetry.ml.cli_params import forecaster_params
from iot_hub.apps.telemetry.ml.forecast_evaluation import rolling_origin_backtest


class Command(BaseCommand):
    help = "Сравнение методов прогнозирования (rolling-origin backtest)"

    def add_arguments(self, parser):
        parser.add_argument("--device", default=None)
        parser.add_argument("--metric", default=None)
        parser.add_argument("--method", default="naive",
                            help="naive, holtwinters, lstm, lstm_lf_resid, auto")
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
        # предиктивные алерты: прогноз пересекает порог AlertThreshold
        parser.add_argument("--write-alerts", action="store_true",
                            help="создавать Alert(source=ml_forecast), если прогноз выходит за порог")
        parser.add_argument("--dedup-hours", type=int, default=6,
                            help="--write-alerts: окно дедупликации предиктивных алертов (часы)")
        # lstm-специфичные
        parser.add_argument("--window", type=int, default=144)
        parser.add_argument("--epochs", type=int, default=100)
        parser.add_argument("--lr", type=float, default=1e-3)
        parser.add_argument("--hidden", type=int, default=32)
        # кэш весов (Фаза 4): применяется к финальной модели для --write-alerts,
        # backtest НЕ кэшируется (каждый origin обучается заново — иначе ложь в метриках)
        parser.add_argument("--use-cache", action="store_true",
                            help="--write-alerts: грузить веса финальной модели из ml/models/")
        parser.add_argument("--save-cache", action="store_true",
                            help="--use-cache: пересохранить веса после обучения на miss")
        # авто-выбор (инкр.6): --method auto
        parser.add_argument("--reselect", action="store_true",
                            help="--method auto: форсировать переоценку HW vs LSTM на hold-out "
                                 "(готовые веса, без torch) вместо чтения готового selection-файла")

    def handle(self, *args, **opts):
        qs = Device.objects.prefetch_related("metrics")
        if opts["device"]:
            qs = qs.filter(serial_number=opts["device"])
        devices = list(qs)
        if not devices:
            self.stderr.write(self.style.ERROR("Устройства не найдены"))
            return

        results = []
        alerts_created = 0
        for device in devices:
            metrics = device.metrics.all()
            if opts["metric"]:
                metrics = [m for m in metrics if m.metric_type == opts["metric"]]
            for metric in metrics:
                series = load_series(device, metric)
                if len(series) < opts["initial_train"] + opts["horizon"]:
                    continue

                # --method auto: per (device, metric) выбираем реальный метод оценкой
                # ГОТОВЫХ весов на hold-out (без torch, инкр.7). Возвращает метод для алертов.
                is_auto = opts["method"] == "auto"
                method = self._auto_select(device, metric, series, opts) \
                    if is_auto else opts["method"]

                factory = lambda m=method: build_forecaster(
                    m, **self._method_params(opts, m))
                # inference-only методы (lstm_lf_resid_onnx) не умеют fit на каждом origin —
                # backtest для них неприменим; работают только в --use-cache (load+forecast).
                if getattr(factory(), "inference_only", False):
                    if not opts["use_cache"]:
                        self.stderr.write(self.style.ERROR(
                            f"Метод '{method}' — только инференс: требуется --use-cache "
                            f"({device.serial_number}/{metric.metric_type} пропущен)."))
                        continue
                elif not is_auto:
                    # backtest — только для ЯВНОГО метода (научный отчёт MAE/RMSE/sMAPE).
                    # При auto оценка уже сделана в _auto_select (hold-out, без переобучения) —
                    # повторный 10-origin backtest дал бы второй, расходящийся MAE в логе.
                    res = rolling_origin_backtest(
                        factory, series, horizon=opts["horizon"],
                        initial_train=opts["initial_train"], step=opts["step"],
                        max_origins=opts["max_origins"])
                    if res["n_origins"]:
                        results.append((device, metric, method, res))

                if opts["write_alerts"]:
                    alerts_created += self._write_forecast_alert(
                        device, metric, series, factory, opts)

        if opts["write_alerts"]:
            self.stdout.write(self.style.SUCCESS(
                f"\nСоздано предиктивных алертов: {alerts_created}"))

        # auto и inference-only методы не дают backtest-результатов (см. выше) — их вывод =
        # выбор/алерты (уже залогированы). Пустой results для них норма, не «нет рядов».
        if not results:
            if not opts["write_alerts"] and opts["method"] != "auto":
                self.stderr.write(self.style.ERROR("Нет рядов достаточной длины"))
            return

        if opts["report"] == "json":
            self._report_json(results, opts)
        else:
            self._report_text(results, opts)

    def _method_params(self, opts, method=None) -> dict:
        return forecaster_params(method or opts["method"], opts)

    def _auto_select(self, device, metric, series, opts) -> str:
        """--method auto: оценка готовых весов на hold-out (БЕЗ torch, инкр.7) → метод.

        HW переобучается на срезе (statsmodels), LSTM — готовый ONNX (forecast_from);
        сравниваем MAE на hold-out, выбираем лучший. Оценка дёшева и без torch →
        выполняется всегда, в т.ч. на Render: выбор честен по фактическому ряду.
        --reselect форсирует пересчёт даже при наличии selection-файла (иначе он
        просто перезаписывается свежей оценкой — она недорогая).
        """
        from iot_hub.apps.telemetry.ml.forecaster_select import (
            evaluate_and_select, load_selection, onnx_available,
            resolve_inference_method, save_selection, selection_key,
        )

        sel_path = selection_key(device.serial_number, metric.metric_type)
        sn, mt = device.serial_number, metric.metric_type

        sel = None if opts["reselect"] else load_selection(sel_path)
        if sel is None:
            sel = evaluate_and_select(
                series, device_sn=sn, metric_type=mt,
                horizon=opts["horizon"], seasonal_periods=opts["seasonal_periods"])
            save_selection(sel_path, sel)
            self.stdout.write(self.style.SUCCESS(
                f"  [auto] {sn}/{mt}: best={sel['best_method']} "
                f"(mae_hw={sel['mae_hw']} mae_lstm={sel['mae_lstm']}) → {sel_path.name}"))
        else:
            # кеш-хит (типичный Render-сценарий --use-cache): всё равно показываем выбор
            self.stdout.write(
                f"  [auto] {sn}/{mt}: best={sel['best_method']} (из selection-файла)")

        has_onnx = onnx_available(sn, mt)
        method = resolve_inference_method(sel, onnx_available=has_onnx)
        if sel.get("best_method") == "lstm_lf_resid" and not has_onnx:
            self.stdout.write(self.style.WARNING(
                f"  [auto] {sn}/{mt}: выбран LSTM, но .onnx не найден → fallback на holtwinters"))
        return method

    def _final_model(self, factory, series, device, metric, opts):
        """Финальная модель для предиктивного алерта: с --use-cache грузит веса,
        иначе обучает на всём ряде. Backtest сюда не относится — он всегда переобучает."""
        model = factory()
        if not opts["use_cache"]:
            return model.fit(series)

        from iot_hub.apps.telemetry.ml.persistence import (
            CacheMismatchError, model_key,
        )

        stem = model_key(model.name, device.serial_number, metric.metric_type)
        try:
            model.load(stem)
            self.stdout.write(self.style.SUCCESS(f"  [cache] загружено: {stem.name}"))
            return model
        except (FileNotFoundError, CacheMismatchError) as e:
            self.stdout.write(f"  [cache] miss ({type(e).__name__}) → обучение")
            model.fit(series)
            if opts["save_cache"]:
                model.save(stem)
                self.stdout.write(f"  [cache] сохранено: {stem.name}")
            return model

    def _write_forecast_alert(self, device, metric, series, factory, opts):
        """Создаёт предиктивный алерт, если прогноз пересекает активный порог.

        Обучаемся на всём ряде, прогнозируем horizon вперёд и через
        predict_threshold_crossing находим первую точку за самым жёстким порогом.
        Возвращает 1, если создан НОВЫЙ алерт (иначе 0 — дубль или нет пересечения).
        """
        from iot_hub.apps.alerts.application.ml_alerts import create_ml_alert
        from iot_hub.apps.devices.models import AlertThreshold
        from iot_hub.apps.telemetry.ml.forecast_base import infer_step
        from iot_hub.apps.telemetry.ml.predictive_alert import predict_threshold_crossing

        thresholds = list(AlertThreshold.objects.filter(metric=metric, is_active=True))
        if not thresholds:
            return 0

        # самые жёсткие границы среди активных порогов (наибольший lower, наименьший upper)
        lowers = [t.lower_bound for t in thresholds if t.lower_bound is not None]
        uppers = [t.upper_bound for t in thresholds if t.upper_bound is not None]
        lower_bound = max(lowers) if lowers else None
        upper_bound = min(uppers) if uppers else None
        if lower_bound is None and upper_bound is None:
            return 0

        step_min = infer_step(series.timestamps).astype("timedelta64[s]").astype(float) / 60.0
        model = self._final_model(factory, series, device, metric, opts)
        fc = model.forecast(opts["horizon"])
        crossing = predict_threshold_crossing(fc, lower_bound, upper_bound, step_min)
        if not crossing.will_cross:
            return 0

        bound_val = upper_bound if crossing.bound_type == "upper" else lower_bound
        bound_kind = "выше" if crossing.bound_type == "upper" else "ниже"
        # severity — у порога, давшего сработавшую границу
        severity = next(
            (t.severity for t in thresholds
             if (crossing.bound_type == "upper" and t.upper_bound == bound_val)
             or (crossing.bound_type == "lower" and t.lower_bound == bound_val)),
            "warning")
        lead_hours = round(crossing.lead_time_hours, 1)
        value = crossing.crossing_value

        _, created = create_ml_alert(
            device=device, metric=metric, source="ml_forecast",
            severity=severity, value=value, message=(
                f"Предиктивный алерт ({fc.meta['method']}): {metric.name} "
                f"выйдет {bound_kind} порога {bound_val} {metric.unit} "
                f"через ~{lead_hours} ч (прогноз {value:.2f})"),
            dedup_hours=opts["dedup_hours"],
            metadata={
                "method": fc.meta["method"],
                "lead_time_hours": lead_hours,
                "forecast_value": round(value, 4),
                "bound": bound_val,
                "bound_kind": bound_kind,
                "horizon": opts["horizon"],
            },
        )
        return 1 if created else 0

    def _report_text(self, results, opts):
        for device, metric, method, res in results:
            self.stdout.write(
                f"\n{device.serial_number} / {metric.metric_type}  "
                f"(метод={method}, горизонт={opts['horizon']}, "
                f"origins={res['n_origins']})")
            self.stdout.write(
                f"  MAE={res['mae']:.3f}  RMSE={res['rmse']:.3f}  sMAPE={res['mape']:.1f}%")

    def _report_json(self, results, opts):
        payload = [
            {
                "device": d.serial_number, "metric": m.metric_type,
                "method": method, "horizon": opts["horizon"],
                "mae": round(r["mae"], 4), "rmse": round(r["rmse"], 4),
                "smape": round(r["mape"], 2), "n_origins": r["n_origins"],
            }
            for d, m, method, r in results
        ]
        self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
