"""Экспорт обученного lstm_lf_resid из .pt в .onnx (Фаза 4, инкр. 5).

Боевой инференс на проде идёт без torch, через onnxruntime (метод
`lstm_lf_resid_onnx`). Эта команда берёт уже обученный артефакт (`.pt` + `.npz` +
`_hw.joblib`, лежит в ml/models/ после train_models или скачивания из Colab) и
дописывает рядом `.onnx`. Запускается локально или на Render Shell (где нет Colab).

Горизонт зашит в граф сети (build_lstm_seq2seq): экспортируем под --horizon
(дефолт 36 = дефолт forecast_telemetry). Инференс этим же горизонтом.

Примеры:
    python manage.py export_onnx_models --device TEMP-001 --metric temperature
    python manage.py export_onnx_models                      # все temperature-ряды
"""
from django.core.management.base import BaseCommand

from iot_hub.apps.devices.models import Device
from iot_hub.apps.telemetry.ml.cli_params import forecaster_params
from iot_hub.apps.telemetry.ml.forecasters import build_forecaster
from iot_hub.apps.telemetry.ml.persistence import CacheMismatchError, model_key

METHOD = "lstm_lf_resid"  # обученный торч-класс (его export_onnx даёт .onnx)


class Command(BaseCommand):
    help = "Экспортировать обученный lstm_lf_resid из .pt в .onnx для боевого инференса"

    def add_arguments(self, parser):
        parser.add_argument("--device", default=None,
                            help="serial_number (по умолчанию — все)")
        parser.add_argument("--metric", default="temperature",
                            help="metric_type (по умолчанию temperature)")
        parser.add_argument("--horizon", type=int, default=36,
                            help="горизонт прогноза — зашивается в ONNX-граф (дефолт 36)")
        parser.add_argument("--opset", type=int, default=17)

    def handle(self, *args, **opts):
        qs = Device.objects.prefetch_related("metrics")
        if opts["device"]:
            qs = qs.filter(serial_number=opts["device"])
        devices = list(qs)
        if not devices:
            self.stderr.write(self.style.ERROR("Устройства не найдены"))
            return

        exported = 0
        for device in devices:
            for metric in device.metrics.all():
                if opts["metric"] and metric.metric_type != opts["metric"]:
                    continue
                stem = model_key(METHOD, device.serial_number, metric.metric_type)
                # грузим обученный артефакт (sha сверяется с дефолтами lstm_lf_resid)
                model = build_forecaster(METHOD, **forecaster_params(METHOD, opts))
                try:
                    model.load(stem)
                except FileNotFoundError:
                    continue  # артефакт не обучен для этого ряда — пропускаем
                except CacheMismatchError as e:
                    self.stderr.write(self.style.WARNING(
                        f"  {stem.name}: пропуск (несовпадение sha): {e}"))
                    continue
                # строим сеть из state_dict (lazy _model) под нужный горизонт
                model.forecast(opts["horizon"])
                if model._model is None:
                    self.stderr.write(self.style.WARNING(
                        f"  {stem.name}: только HW (ряд короче окна) — ONNX не нужен"))
                    continue
                path = model.export_onnx(stem, opset=opts["opset"])
                exported += 1
                self.stdout.write(f"  {device.serial_number}/{metric.metric_type} → {path}")

        if not exported:
            self.stderr.write(self.style.ERROR(
                "Нечего экспортировать: обучи lstm_lf_resid (train_models) или "
                "скачай веса из Colab в ml/models/"))
            return
        self.stdout.write(self.style.SUCCESS(f"\nЭкспортировано ONNX-моделей: {exported}"))
