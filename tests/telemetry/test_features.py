"""Юнит-тесты извлечения признаков. Чистый numpy, без БД."""
import numpy as np

from iot_hub.apps.telemetry.ml.features import build_features, FEATURE_NAMES


def _noisy(n=200, seed=0):
    return np.random.default_rng(seed).normal(50.0, 1.0, n)


def test_shape():
    X, warmup = build_features(_noisy(), window=24)
    assert X.shape == (200, len(FEATURE_NAMES)) == (200, 7)
    assert warmup.shape == (200,)


def test_no_nan():
    """sklearn упадёт на NaN — матрица должна быть полностью конечной."""
    X, _ = build_features(_noisy(), window=24)
    assert np.isfinite(X).all()


def test_warmup_mask():
    _, warmup = build_features(_noisy(), window=24)
    assert warmup[:24].all()
    assert not warmup[24:].any()


def test_causality_no_lookahead():
    """Изменение точки t не влияет на признаки точек левее t (нет look-ahead)."""
    values = _noisy()
    X_base, _ = build_features(values.copy(), window=24)
    spiked = values.copy()
    spiked[150] += 10.0
    X_after, _ = build_features(spiked, window=24)
    # все строки до 150 (точка t использует только прошлое) идентичны
    np.testing.assert_array_equal(X_base[:150], X_after[:150])


def test_stuck_low_roll_std():
    """На залипшем участке roll_std≈0, на нормальном >0 — фича различает stuck."""
    values = _noisy(n=200)
    values[100:150] = 50.0  # залипание
    X, _ = build_features(values, window=24)
    std_idx = FEATURE_NAMES.index("roll_std")
    # точка глубоко внутри stuck (окно целиком в константе) → std≈0
    assert X[140, std_idx] < 1e-6
    # нормальная точка → std заметно больше
    assert X[60, std_idx] > 0.1


def test_short_series():
    """Ряд короче окна: всё warmup, без падения."""
    X, warmup = build_features(_noisy(n=10), window=24)
    assert warmup.all()
    assert np.isfinite(X).all()
