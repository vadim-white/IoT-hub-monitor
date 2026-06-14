"""Тесты LSTMLfResidOnnxForecaster (Фаза 4, инкр. 5).

ONNX-инференс гибрида HW + level-fix LSTM без torch. Главный тест — паритет ONNX-вывода
с torch-выводом (train once, deploy anywhere). Требует torch+statsmodels (обучение/
экспорт) И onnxruntime (инференс) — пропускается без любого. Целевой прогон — Docker.
"""
import numpy as np
import pytest

pytest.importorskip("torch")
pytest.importorskip("statsmodels")
pytest.importorskip("onnxruntime")

from iot_hub.apps.telemetry.ml.dataset import TimeSeries
from iot_hub.apps.telemetry.ml.forecasters import build_forecaster
from iot_hub.apps.telemetry.ml.forecasters.lstm_level_fix_residual import (
    LSTMLevelFixResidualForecaster,
)
from iot_hub.apps.telemetry.ml.forecasters.lstm_lf_resid_onnx import (
    LSTMLfResidOnnxForecaster,
)
from iot_hub.apps.telemetry.ml.persistence import CacheMismatchError


def _series(values: np.ndarray) -> TimeSeries:
    n = len(values)
    ts = np.datetime64("2025-01-01") + np.arange(n) * np.timedelta64(10, "m")
    return TimeSeries(timestamps=ts, values=values.astype(float))


def _trend_season(n=900, period=144, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    return (50 + 0.002 * t + 5 * np.sin(2 * np.pi * t / period)
            + rng.normal(0, 0.4, n))


# те же гиперпараметры, что у торч-теста → sha артефакта совпадает между классами
_OPTS = dict(window=144, epochs=12, hidden=8, seasonal_periods=144, random_state=7)
_H = 36


def _train_export(tmp_path, horizon=_H):
    """Обучить торч-класс, посчитать torch-прогноз, сохранить + экспортировать .onnx."""
    s = _series(_trend_season())
    torch_model = LSTMLevelFixResidualForecaster(**_OPTS).fit(s)
    torch_fc = torch_model.forecast(horizon)  # строит сеть под horizon
    assert torch_model._model is not None
    stem = tmp_path / "lstm_lf_resid__d__m"
    torch_model.save(stem)
    torch_model.export_onnx(stem)
    return stem, torch_fc


def test_onnx_matches_torch(tmp_path):
    """ONNX-инференс ≈ torch-инференс (главный тест инкр.5)."""
    stem, torch_fc = _train_export(tmp_path)
    onnx_model = LSTMLfResidOnnxForecaster(**_OPTS).load(stem)
    onnx_fc = onnx_model.forecast(_H)
    assert onnx_fc.mean.shape == (_H,)
    assert onnx_fc.meta["method"] == "lstm_lf_resid_onnx"
    np.testing.assert_allclose(onnx_fc.mean, torch_fc.mean, rtol=1e-4, atol=1e-4)


def test_registered_in_build_forecaster():
    model = build_forecaster("lstm_lf_resid_onnx", **_OPTS)
    assert isinstance(model, LSTMLfResidOnnxForecaster)


def test_horizon_mismatch_raises(tmp_path):
    """Граф зашит под _H → forecast другим горизонтом даёт понятную ошибку."""
    stem, _ = _train_export(tmp_path)
    onnx_model = LSTMLfResidOnnxForecaster(**_OPTS).load(stem)
    with pytest.raises(ValueError, match="оризонт зашит"):
        onnx_model.forecast(_H + 6)


def test_persistence_roundtrip(tmp_path):
    """load → forecast → load → forecast идентично (детерминированная сессия)."""
    stem, _ = _train_export(tmp_path)
    a = LSTMLfResidOnnxForecaster(**_OPTS).load(stem).forecast(_H)
    b = LSTMLfResidOnnxForecaster(**_OPTS).load(stem).forecast(_H)
    np.testing.assert_allclose(a.mean, b.mean, rtol=1e-6, atol=1e-6)


def test_cache_invalidation(tmp_path):
    """load объектом с другим window → CacheMismatchError, не тихий неверный вывод."""
    stem, _ = _train_export(tmp_path)
    with pytest.raises(CacheMismatchError):
        LSTMLfResidOnnxForecaster(**{**_OPTS, "window": 72}).load(stem)


def test_fit_not_supported():
    """ONNX-класс только инференс: fit() явно запрещён."""
    with pytest.raises(NotImplementedError):
        LSTMLfResidOnnxForecaster(**_OPTS).fit(_series(_trend_season()))


def test_no_torch_in_inference_module():
    """Sanity: модуль инференса не тянет torch (смысл инкр.5 — прод без torch).

    Проверяем исходник, а не import (torch в тестовой среде есть): в файле не должно
    быть `import torch` ни на уровне модуля, ни в forecast/_load_state.
    """
    import iot_hub.apps.telemetry.ml.forecasters.lstm_lf_resid_onnx as mod

    src = open(mod.__file__, encoding="utf-8").read()
    assert "import torch" not in src
