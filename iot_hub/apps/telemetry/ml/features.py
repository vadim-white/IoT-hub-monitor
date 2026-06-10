"""Извлечение каузальных (trailing) признаков из одномерного ряда для Isolation Forest.

IsolationForest на одном скаляре value вырождается в порог — сила метода в
многомерном признаковом пространстве, которое строит этот модуль. Все признаки
точки t считаются ТОЛЬКО по прошлому окну x[t-window:t] (как z-score): значение
точки t не участвует в её собственных rolling-статистиках. Look-ahead запрещён —
иначе recall нечестно завышается (защищено тестом test_causality_no_lookahead).
"""
from __future__ import annotations

import numpy as np

FEATURE_NAMES: list[str] = [
    "value", "residual", "z_like", "roll_std",
    "roll_range", "diff1", "abs_dev_from_med",
]


def build_features(values: np.ndarray, window: int, eps: float = 1e-9
                   ) -> tuple[np.ndarray, np.ndarray]:
    """Строит матрицу признаков X (n, 7) и warmup_mask (n,).

    X без NaN (sklearn не принимает NaN): warmup-строки заполнены нейтрально,
    но помечены в warmup_mask и исключаются из метрик. Первые `window` точек —
    warmup (нет полного прошлого окна).
    """
    x = np.asarray(values, dtype=float)
    n = len(x)
    X = np.zeros((n, len(FEATURE_NAMES)), dtype=float)
    warmup = np.zeros(n, dtype=bool)

    # diff1 каузален (использует только t и t-1); для t=0 даёт 0
    diff1 = np.diff(x, prepend=x[0])

    if n <= window:
        warmup[:] = True
        X[:, 0] = x
        X[:, 5] = diff1
        return X, warmup

    warmup[:window] = True

    # windows[i] = x[i:i+window]; присваиваем точке t=i+window → ровно x[t-window:t]
    windows = np.lib.stride_tricks.sliding_window_view(x, window)[:-1]
    mu = windows.mean(axis=1)
    sd = windows.std(axis=1)
    rng = windows.max(axis=1) - windows.min(axis=1)
    med = np.median(windows, axis=1)

    sl = slice(window, n)
    xv = x[window:]
    X[sl, 0] = xv                          # value
    X[sl, 1] = xv - mu                     # residual
    X[sl, 2] = (xv - mu) / (sd + eps)      # z_like
    X[sl, 3] = sd                          # roll_std
    X[sl, 4] = rng                         # roll_range
    X[sl, 5] = diff1[window:]              # diff1
    X[sl, 6] = np.abs(xv - med)            # abs_dev_from_med

    return X, warmup
