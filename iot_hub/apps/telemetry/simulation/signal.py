"""Доменное ядро генерации синтетической телеметрии.

Чистый Python + numpy, без зависимостей от Django — переиспользуется и в
management-команде generate_telemetry, и в ML-экспериментах диплома.

Модель сигнала (откалибрована по реальным датасетам, см. docs/simulator/):
    value[t] = base_mean + seasonal(t) + daily(t) + AR1_noise(t)

где:
- seasonal(t): годовой ход (синус, фаза по min_month/max_month из профиля)
- daily(t):    суточный ход (синус, амплитуда/фаза из профиля)
- AR1_noise:   e[t] = ar1*e[t-1] + sqrt(1-ar1²)*N(0,std) — даёт реалистичную
               «гладкость» сигнала (см. ar1_coef в профиле)

Поверх нормального сигнала инжектятся размеченные аномалии (ground-truth для ML).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np


# Типы аномалий — источник идей: NAB artificialWithAnomaly
ANOMALY_TYPES = ("spike", "drift", "stuck", "dropout", "noise_burst")


@dataclass
class GeneratedPoint:
    """Одна точка телеметрии с меткой аномалии (ground-truth)."""
    recorded_at: datetime
    value: float
    is_anomaly: bool = False
    anomaly_type: str | None = None
    anomaly_severity: str | None = None  # low | medium | high
    is_degradation: bool = False         # точка на участке монотонного дрейфа к отказу


@dataclass
class SignalGenerator:
    """Генерирует временной ряд по профилю метрики.

    profile — dict из iot_hub/apps/telemetry/profiles/*.json:
        base_mean, base_std, ar1_coef, min_clip, max_clip,
        daily{amplitude, peak_hour}, seasonal{min_month, max_month, amplitude}
    """
    profile: dict
    rng: np.random.Generator = field(default_factory=lambda: np.random.default_rng())

    # ── компоненты сигнала ──────────────────────────────────────────

    def _daily(self, dt: datetime) -> float:
        """Суточный ход: синус с пиком в profile.daily.peak_hour."""
        d = self.profile.get("daily")
        if not d:
            return 0.0
        amp = d["amplitude"] / 2.0
        peak = d["peak_hour"]
        hour = dt.hour + dt.minute / 60.0
        # косинус сдвинут так, чтобы максимум пришёлся на peak_hour
        phase = 2 * math.pi * (hour - peak) / 24.0
        return amp * math.cos(phase)

    def _seasonal(self, dt: datetime) -> float:
        """Годовой ход: синус с минимумом в min_month, максимумом в max_month."""
        s = self.profile.get("seasonal")
        if not s:
            return 0.0
        amp = s["amplitude"] / 2.0
        max_month = s["max_month"]
        day_of_year = dt.timetuple().tm_yday
        # пик годового хода — в середине max_month
        peak_doy = (max_month - 0.5) / 12.0 * 365.0
        phase = 2 * math.pi * (day_of_year - peak_doy) / 365.0
        return amp * math.cos(phase)

    def _baseline_series(self, timestamps: list[datetime]) -> np.ndarray:
        """Нормальный сигнал (без аномалий): base + seasonal + daily + AR(1)-шум."""
        n = len(timestamps)
        base = self.profile["base_mean"]
        std = self.profile["base_std"]
        ar1 = max(-0.999, min(0.999, self.profile.get("ar1_coef", 0.0)))

        deterministic = np.array(
            [base + self._seasonal(dt) + self._daily(dt) for dt in timestamps],
            dtype=float,
        )

        # AR(1)-шум e[t] = ar1*e[t-1] + innovation. Масштаб инноваций даёт
        # стационарную дисперсию шума ≈ std при заданной автокорреляции ar1.
        innov_scale = std * math.sqrt(1 - ar1 ** 2)
        noise = np.empty(n, dtype=float)
        e = self.rng.normal(0, std)
        for i in range(n):
            e = ar1 * e + self.rng.normal(0, innov_scale)
            noise[i] = e

        return deterministic + noise

    # ── инъекция аномалий ───────────────────────────────────────────

    def _inject_anomalies(
        self, values: np.ndarray, anomaly_rate: float
    ) -> list[tuple[str, str]]:
        """Портит часть ряда аномалиями in-place. Возвращает метки на каждую точку.

        anomaly_rate — доля точек, затронутых аномалиями (0..1).
        Возвращает список (anomaly_type|"", severity|"") длины len(values).
        """
        n = len(values)
        labels: list[tuple[str, str]] = [("", "")] * n
        if anomaly_rate <= 0 or n < 10:
            return labels

        std = self.profile["base_std"]
        target = int(n * anomaly_rate)
        # Эпизод drift/stuck/... ограничен долей бюджета, иначе один «объёмный»
        # тип съедает весь target и остальные типы не попадают в ряд.
        ep_max = max(2, target // 6)

        def free(start: int, end: int) -> bool:
            return all(labels[i][0] == "" for i in range(start, end))

        def mark(start: int, end: int, atype: str, sev: str) -> None:
            for i in range(start, end):
                labels[i] = (atype, sev)

        covered = 0
        guard = 0
        episode = 0
        while covered < target and guard < target * 8:
            guard += 1
            # ротация по типам — гарантирует представленность всех пяти
            atype = ANOMALY_TYPES[episode % len(ANOMALY_TYPES)]
            episode += 1

            if atype == "spike":
                start = int(self.rng.integers(0, n))
                if not free(start, start + 1):
                    continue
                mag = self.rng.uniform(4, 8) * std * self.rng.choice([-1, 1])
                values[start] += mag
                mark(start, start + 1, "spike", "high")
                covered += 1
                continue

            length = int(self.rng.integers(2, ep_max + 1))
            start = int(self.rng.integers(0, max(1, n - length)))
            end = min(start + length, n)
            if not free(start, end):
                continue

            if atype == "drift":
                values[start:end] += np.linspace(0, self.rng.uniform(2, 4) * std, end - start)
                mark(start, end, "drift", "medium")
            elif atype == "stuck":
                values[start:end] = values[start]
                mark(start, end, "stuck", "medium")
            elif atype == "dropout":
                values[start:end] = 0.0
                mark(start, end, "dropout", "high")
            elif atype == "noise_burst":
                values[start:end] += self.rng.normal(0, 3 * std, end - start)
                mark(start, end, "noise_burst", "low")
            covered += end - start

        return labels

    # ── публичный API ───────────────────────────────────────────────

    def generate(
        self,
        start: datetime,
        end: datetime,
        step_minutes: int = 10,
        anomaly_rate: float = 0.0,
        degradation: bool = False,
        degradation_rate: float = 1.0,
        degradation_start_frac: float = 0.4,
    ) -> list[GeneratedPoint]:
        """Строит ряд точек от start до end с шагом step_minutes.

        degradation=True добавляет монотонный дрейф к отказу (как C-MAPSS): со
        второй части ряда значение линейно растёт, выходя за max_clip к концу.
        Это тренд (ground-truth для предиктивного алерта), не точечная аномалия.
        """
        step = timedelta(minutes=step_minutes)
        timestamps: list[datetime] = []
        t = start
        while t < end:
            timestamps.append(t)
            t += step

        values = self._baseline_series(timestamps)
        labels = self._inject_anomalies(values, anomaly_rate)
        degr_mask = self._apply_degradation(
            values, degradation_rate, degradation_start_frac) if degradation \
            else [False] * len(values)

        # Норму клиппим строго по профилю; аномалиям даём расширенный коридор —
        # заметные, но правдоподобные (иначе spike +8σ даёт абсурд вроде +96°C).
        # dropout=0 не клиппим: нулевое «нефизичное» значение и должен ловить ML.
        lo = self.profile.get("min_clip")
        hi = self.profile.get("max_clip")
        if lo is not None and hi is not None:
            margin = 0.5 * (hi - lo)
            anom_lo, anom_hi = lo - margin, hi + margin
        else:
            anom_lo = anom_hi = None

        points: list[GeneratedPoint] = []
        for dt, val, (atype, sev), is_degr in zip(timestamps, values, labels, degr_mask):
            v = float(val)
            # деградирующие точки НЕ клиппим — тренд должен выйти за порог
            if lo is not None and hi is not None and not is_degr:
                if not atype:
                    v = max(lo, min(hi, v))
                elif atype != "dropout":
                    v = max(anom_lo, min(anom_hi, v))
            points.append(
                GeneratedPoint(
                    recorded_at=dt,
                    value=round(v, 4),
                    is_anomaly=bool(atype),
                    anomaly_type=atype or None,
                    anomaly_severity=sev or None,
                    is_degradation=bool(is_degr),
                )
            )
        return points

    def _apply_degradation(self, values: np.ndarray, rate: float,
                           start_frac: float) -> list[bool]:
        """Добавляет монотонный линейный дрейф со start_frac·n до конца ряда.

        К концу значение поднимается на rate·(max_clip-min_clip) сверх диапазона
        профиля, гарантированно выходя за max_clip — модель деградации оборудования.
        Возвращает маску точек, затронутых дрейфом (ground-truth тренда).
        """
        n = len(values)
        start = int(n * start_frac)
        span = self.profile.get("max_clip", values.max()) - \
            self.profile.get("min_clip", values.min())
        peak = rate * span * 1.2   # к концу выходим на 120% диапазона за max_clip
        ramp = np.zeros(n)
        if start < n - 1:
            ramp[start:] = np.linspace(0, peak, n - start)
        values += ramp
        return [i >= start for i in range(n)]
