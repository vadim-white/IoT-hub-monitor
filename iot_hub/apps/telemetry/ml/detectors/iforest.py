"""Детектор аномалий на Isolation Forest (sklearn).

В отличие от z-score, работает в многомерном признаковом пространстве (ml/features.py)
и потому ловит аномалии без выброса дисперсии — залипание (stuck) и пропадание
(dropout), на которых z-score структурно слеп.

Обучение unsupervised на ВСЕХ точках ряда (метки не используются — честно по
сравнению с z-score; метки только в evaluation). contamination — гиперпараметр
ожидаемой доли аномалий, а не подсмотренные метки.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.ensemble import IsolationForest

from ..base import AnomalyDetector, DetectionResult
from ..dataset import TimeSeries
from ..features import build_features, FEATURE_NAMES
from ..persistence import ModelPersistenceMixin


@dataclass
class IsolationForestDetector(ModelPersistenceMixin, AnomalyDetector):
    """window — окно для признаков; threshold — порог по score (=-decision_function).

    threshold=0.0 воспроизводит штатный sklearn-predict при данной contamination;
    сдвиг порога даёт sweep-кривую, сопоставимую с z-score.
    """
    window: int = 72
    threshold: float = 0.0
    contamination: float = 0.02
    n_estimators: int = 200
    random_state: int = 42
    name: str = "iforest"
    _model: IsolationForest | None = field(default=None, init=False, repr=False)

    def fit(self, series: TimeSeries) -> "IsolationForestDetector":
        X, _ = build_features(np.asarray(series.values, float), self.window)
        self._model = IsolationForest(
            n_estimators=self.n_estimators,
            contamination=self.contamination,
            random_state=self.random_state,
        ).fit(X)
        return self

    def score(self, series: TimeSeries) -> np.ndarray:
        if self._model is None:
            self.fit(series)
        X, _ = build_features(np.asarray(series.values, float), self.window)
        # decision_function: высокий = норма; инвертируем → больше = аномальнее
        return -self._model.decision_function(X)

    def predict(self, series: TimeSeries) -> DetectionResult:
        if self._model is None:
            self.fit(series)
        X, warmup = build_features(np.asarray(series.values, float), self.window)
        scores = -self._model.decision_function(X)
        predictions = (scores >= self.threshold) & ~warmup
        return DetectionResult(
            scores=scores,
            predictions=predictions,
            warmup_mask=warmup,
            threshold=self.threshold,
            meta={
                "method": self.name,
                "window": self.window,
                "params": {
                    "threshold": self.threshold,
                    "contamination": self.contamination,
                    "n_estimators": self.n_estimators,
                    "random_state": self.random_state,
                    "features": FEATURE_NAMES,
                },
            },
        )

    # --- персистентность: sklearn-модель через joblib ---
    def _dump_state(self, stem) -> None:
        if self._model is None:
            raise ValueError("Нечего сохранять: вызовите fit() перед save()")
        import joblib  # зависимость scikit-learn; импорт локальный

        joblib.dump(self._model, f"{stem}.joblib")

    def _load_state(self, stem, manifest) -> None:
        import joblib

        self._model = joblib.load(f"{stem}.joblib")
