"""Baseline-детектор: скользящий z-score.

z[t] = (x[t] - mean(окно)) / std(окно), аномалия при |z| >= threshold.
Окно trailing (causal): статистика по прошлым точкам x[t-window:t], БЕЗ самой
точки t — иначе выброс размывает собственную статистику и маскирует сам себя,
а оценка получает look-ahead и нечестно завышает recall. Trailing-окно ещё и
моделирует реальный онлайн-детектор → корректно меряется время до детекции.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..base import AnomalyDetector, DetectionResult
from ..dataset import TimeSeries
from ..persistence import ModelPersistenceMixin


@dataclass
class ZScoreDetector(ModelPersistenceMixin, AnomalyDetector):
    """Скользящий z-score. Полностью детерминирован (нет ГСЧ).

    window    — точек в окне. При шаге 10 мин: 24 = 4 часа, 144 = сутки
    threshold — порог по |z|
    min_std   — защита от деления на ноль на «плоских» участках (stuck/dropout)
    """
    window: int = 24
    threshold: float = 3.0
    min_std: float = 1e-9
    name: str = "zscore"

    def _rolling_stats(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Trailing mean/std: для точки t — по x[t-window:t] (прошлое, без t).

        Возвращает массивы (n,), где первые window точек = NaN (нет полной истории).
        """
        n = len(x)
        mean = np.full(n, np.nan)
        std = np.full(n, np.nan)
        if n <= self.window:
            return mean, std
        # windows[i] = x[i:i+window]; присваиваем точке t=i+window, поэтому
        # для t берётся ровно x[t-window:t] (прошлое, без самой t)
        windows = np.lib.stride_tricks.sliding_window_view(x, self.window)
        mean[self.window:] = windows[:-1].mean(axis=1)
        std[self.window:] = windows[:-1].std(axis=1)
        return mean, std

    def score(self, series: TimeSeries) -> np.ndarray:
        x = np.asarray(series.values, dtype=float)
        mean, std = self._rolling_stats(x)
        std = np.where(std < self.min_std, np.nan, std)
        z = (x - mean) / std
        return np.abs(np.nan_to_num(z, nan=0.0))

    def predict(self, series: TimeSeries) -> DetectionResult:
        scores = self.score(series)
        n = len(series)
        warmup = np.zeros(n, dtype=bool)
        warmup[: self.window] = True
        predictions = (scores >= self.threshold) & ~warmup
        return DetectionResult(
            scores=scores,
            predictions=predictions,
            warmup_mask=warmup,
            threshold=self.threshold,
            meta={
                "method": self.name,
                "window": self.window,
                "params": {"threshold": self.threshold, "min_std": self.min_std},
            },
        )

    # --- персистентность: детектор stateless, веса хранить нечего ---
    def _dump_state(self, stem) -> None:
        """Состояния нет (онлайновый метод) — артефакт = только манифест."""

    def _load_state(self, stem, manifest) -> None:
        """Восстанавливать нечего; sha уже сверён в ModelPersistenceMixin.load."""
