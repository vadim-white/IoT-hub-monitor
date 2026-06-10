"""Генератор синтетической телеметрии, откалиброванной по реальным датасетам.

Заменяет старую «дневную» телеметрию плотным рядом (шаг 10 мин по умолчанию)
с реалистичной формой сигнала и размеченными аномалиями (ground-truth для ML).

Примеры:
    python manage.py generate_telemetry --days 30
    python manage.py generate_telemetry --days 60 --step-minutes 10 --anomaly-rate 0.03 --seed 42
    python manage.py generate_telemetry --devices TEMP-001 TEMP-003 --keep-existing

Метки аномалий пишутся в Telemetry.raw_data['anomaly'] (см. docs/simulator/SIMULATOR_DESIGN.md).
Режим записи пока один — прямой bulk_create в БД (--transport=db). Live-режим — позже.
"""
import json
import os

import numpy as np
from django.core.management.base import BaseCommand
from django.utils import timezone

from iot_hub.apps.devices.models import Device, AlertThreshold
from iot_hub.apps.telemetry.models import Telemetry
from iot_hub.apps.telemetry.simulation.signal import SignalGenerator

PROFILES_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "profiles")

# Маркеры «уличного» размещения в location_name (иначе считаем датчик комнатным)
OUTDOOR_HINTS = ("улиц", "крыш", "снаруж", "outdoor", "street")


def _is_outdoor(device) -> bool:
    loc = (device.location_name or "").lower()
    return any(h in loc for h in OUTDOOR_HINTS)


def _profile_name_for(metric_type: str, device) -> str | None:
    """Сопоставляет metric_type устройства имени файла профиля."""
    if metric_type in ("temperature", "humidity"):
        suffix = "outdoor" if _is_outdoor(device) else "indoor"
        return f"{metric_type}_{suffix}"
    if metric_type in ("voltage", "current", "power"):
        return metric_type
    # rssi/uptime/error_count/custom — профилей пока нет (см. SIMULATOR_DESIGN.md)
    return None


class Command(BaseCommand):
    help = "Генерирует синтетическую телеметрию по профилям, откалиброванным по реальным датасетам"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30,
                            help="Сколько дней истории сгенерировать (по умолчанию 30)")
        parser.add_argument("--step-minutes", type=int, default=10,
                            help="Шаг между точками в минутах (по умолчанию 10)")
        parser.add_argument("--anomaly-rate", type=float, default=0.02,
                            help="Доля аномальных точек 0..1 (по умолчанию 0.02)")
        parser.add_argument("--seed", type=int, default=None,
                            help="Seed ГСЧ для воспроизводимости экспериментов")
        parser.add_argument("--devices", nargs="*", default=None,
                            help="Серийные номера устройств (по умолчанию — все)")
        parser.add_argument("--keep-existing", action="store_true",
                            help="Не удалять старую телеметрию (по умолчанию заменяем)")
        parser.add_argument("--transport", choices=["db"], default="db",
                            help="Режим записи: db = прямой bulk_create (пока единственный)")

    def handle(self, *args, **opts):
        days = opts["days"]
        step = opts["step_minutes"]
        anomaly_rate = opts["anomaly_rate"]
        seed = opts["seed"]
        keep = opts["keep_existing"]

        # Загружаем профили один раз
        profiles = self._load_profiles()
        if not profiles:
            self.stderr.write(self.style.ERROR(
                f"Профили не найдены в {PROFILES_DIR}. Сначала запусти tools/extract_profiles.py"))
            return

        # Выбор устройств
        qs = Device.objects.prefetch_related("metrics")
        if opts["devices"]:
            qs = qs.filter(serial_number__in=opts["devices"])
        devices = list(qs)
        if not devices:
            self.stderr.write(self.style.ERROR("Устройства не найдены"))
            return

        end = timezone.now()
        start = end - timezone.timedelta(days=days)

        # Базовый seed: на каждое устройство+метрику делаем свой поток ГСЧ,
        # чтобы результат был воспроизводим и при этом ряды не были идентичны.
        base_seed = seed if seed is not None else int(np.random.SeedSequence().entropy % (2**32))

        total = 0
        skipped_metrics = 0
        for device in devices:
            for metric in device.metrics.all():
                pname = _profile_name_for(metric.metric_type, device)
                if pname is None or pname not in profiles:
                    skipped_metrics += 1
                    continue

                mseed = abs(hash((base_seed, device.serial_number, metric.metric_type))) % (2**32)
                gen = SignalGenerator(profiles[pname], rng=np.random.default_rng(mseed))
                points = gen.generate(start, end, step_minutes=step, anomaly_rate=anomaly_rate)

                thresholds = list(AlertThreshold.objects.filter(metric=metric, is_active=True))

                if not keep:
                    Telemetry.objects.filter(device=device, metric=metric).delete()

                rows = []
                for p in points:
                    rows.append(Telemetry(
                        device=device,
                        metric=metric,
                        value=p.value,
                        unit=metric.unit,
                        status=self._status_for(p.value, thresholds),
                        recorded_at=p.recorded_at,
                        raw_data={
                            "synthetic": True,
                            "profile": pname,
                            "anomaly": {
                                "is_anomaly": p.is_anomaly,
                                **({"type": p.anomaly_type, "severity": p.anomaly_severity}
                                   if p.is_anomaly else {}),
                            },
                        },
                    ))
                Telemetry.objects.bulk_create(rows, batch_size=2000)
                total += len(rows)
                self.stdout.write(
                    f"  {device.serial_number:<12} {metric.metric_type:<12} "
                    f"← {pname:<20} {len(rows)} точек")

            # Обновляем устройство «как живое»
            device.last_seen_at = end
            device.status = "active"
            device.save(update_fields=["last_seen_at", "status"])

        self.stdout.write(self.style.SUCCESS(
            f"\nГотово: {total} точек телеметрии для {len(devices)} устройств "
            f"(шаг {step} мин, {days} дн, аномалии {anomaly_rate:.0%}). "
            f"Пропущено метрик без профиля: {skipped_metrics}."))
        if seed is not None:
            self.stdout.write(f"Seed={seed} — результат воспроизводим.")

    def _load_profiles(self) -> dict:
        profiles = {}
        if not os.path.isdir(PROFILES_DIR):
            return profiles
        for fn in os.listdir(PROFILES_DIR):
            if fn.endswith(".json"):
                with open(os.path.join(PROFILES_DIR, fn), encoding="utf-8") as f:
                    profiles[fn[:-5]] = json.load(f)
        return profiles

    @staticmethod
    def _status_for(value: float, thresholds) -> str:
        """Статус точки по порогам: critical→error, warning→warning, иначе ok."""
        status = "ok"
        for t in thresholds:
            if t.check_threshold(value):
                if t.severity == "critical":
                    return "error"
                if t.severity == "warning":
                    status = "warning"
        return status
