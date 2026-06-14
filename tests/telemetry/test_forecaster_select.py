"""Тесты авто-выбора форкастера HW vs LSTM на hold-out (Фаза 4, инкр. 6–7).

Оценка готовых весов БЕЗ переобучения: HW (fit на срезе) и LSTM (готовый ONNX
forecast_from) прогнозируют hold-out → MAE → выбор. Тесты мокают HW-fit и загрузку
ONNX, чтобы гоняться без torch/onnxruntime — проверяем правила отбора, fallback,
персистентность и резолв инференс-метода.
"""
import numpy as np
import pytest

from iot_hub.apps.telemetry.ml import forecaster_select as fs
from iot_hub.apps.telemetry.ml.dataset import TimeSeries
from iot_hub.apps.telemetry.ml.forecast_base import ForecastResult

HORIZON = 36


def _series(n=400):
    ts = np.datetime64("2025-01-01") + np.arange(n) * np.timedelta64(10, "m")
    # детерминированный, но не плоский ряд (чтобы truth был содержательным)
    vals = 50 + np.sin(np.arange(n) / 12.0)
    return TimeSeries(timestamps=ts, values=vals)


def _fc(mean):
    return ForecastResult(timestamps=None, mean=np.asarray(mean, float),
                          lower=None, upper=None, horizon=len(mean), meta={})


class _StubHW:
    """HW-стаб: fit() no-op, forecast() отдаёт заранее заданный прогноз."""
    def __init__(self, pred):
        self._pred = pred

    def fit(self, series):
        return self

    def forecast(self, horizon):
        return _fc(self._pred[:horizon])


class _StubOnnx:
    def __init__(self, pred):
        self._pred = pred

    def forecast_from(self, series, horizon):
        return _fc(self._pred[:horizon])


def _setup(monkeypatch, hw_pred, lstm_pred):
    """Подменяет HW-фабрику и загрузку ONNX заданными прогнозами на hold-out.

    hw_pred / lstm_pred — массивы длины HORIZON (или None, чтобы метод 'отсутствовал')."""
    monkeypatch.setattr(
        fs, "build_forecaster",
        lambda method, **kw: _StubHW(hw_pred) if hw_pred is not None else _raise())
    monkeypatch.setattr(
        fs, "_load_onnx",
        lambda sn, mt, sp: _StubOnnx(lstm_pred) if lstm_pred is not None else None)


def _raise():
    raise RuntimeError("HW недоступен")


def _eval(series=None):
    return fs.evaluate_and_select(
        series or _series(), device_sn="TEMP-001", metric_type="temperature",
        horizon=HORIZON)


def _truth(series):
    n = len(series.values)
    cut = n - HORIZON
    return series.values[cut:cut + HORIZON]


def test_select_prefers_lower_mae(monkeypatch):
    s = _series()
    truth = _truth(s)
    # LSTM ближе к truth → меньше MAE → выбирается
    _setup(monkeypatch, hw_pred=truth + 0.5, lstm_pred=truth + 0.1)
    sel = _eval(s)
    assert sel["best_method"] == fs.LSTM_METHOD
    assert sel["mae_lstm"] < sel["mae_hw"]
    assert sel["eval"] == "holdout_ready_weights" and sel["holdout"] == HORIZON


def test_select_keeps_hw_when_hw_better(monkeypatch):
    s = _series()
    truth = _truth(s)
    # кейс TEMP-004: HW точнее → честно HW
    _setup(monkeypatch, hw_pred=truth + 0.1, lstm_pred=truth + 0.5)
    assert _eval(s)["best_method"] == fs.HW_METHOD


def test_select_falls_back_to_hw_on_tie(monkeypatch):
    s = _series()
    truth = _truth(s)
    _setup(monkeypatch, hw_pred=truth + 0.3, lstm_pred=truth + 0.3)
    assert _eval(s)["best_method"] == fs.HW_METHOD  # равенство → HW


def test_select_falls_back_to_hw_when_no_onnx(monkeypatch):
    s = _series()
    truth = _truth(s)
    _setup(monkeypatch, hw_pred=truth + 0.2, lstm_pred=None)  # ONNX нет
    sel = _eval(s)
    assert sel["best_method"] == fs.HW_METHOD and sel["mae_lstm"] is None


def test_select_hw_when_series_too_short(monkeypatch):
    _setup(monkeypatch, hw_pred=np.zeros(HORIZON), lstm_pred=np.zeros(HORIZON))
    short = _series(n=HORIZON)  # cut = 0 → нет прошлого для прогноза
    sel = fs.evaluate_and_select(
        short, device_sn="X", metric_type="temperature", horizon=HORIZON)
    assert sel["best_method"] == fs.HW_METHOD
    assert sel["mae_hw"] is None and sel["mae_lstm"] is None


def test_select_holdout_shorter_than_horizon(monkeypatch):
    """holdout < horizon: оценка на eval_len=min точек, без shape-mismatch (инкр.7 fix)."""
    s = _series(n=400)
    # прогноз длиной horizon, truth усечётся до holdout=20 внутри функции
    hw_pred = np.zeros(HORIZON)
    lstm_pred = np.zeros(HORIZON)
    monkeypatch.setattr(fs, "build_forecaster", lambda method, **kw: _StubHW(hw_pred))
    monkeypatch.setattr(fs, "_load_onnx", lambda sn, mt, sp: _StubOnnx(lstm_pred))
    sel = fs.evaluate_and_select(
        s, device_sn="X", metric_type="temperature", horizon=HORIZON, holdout=20)
    assert sel["holdout"] == 20 and sel["mae_hw"] is not None  # не упало


def test_save_load_selection_roundtrip(tmp_path):
    path = tmp_path / "x_forecaster_select.json"
    payload = {"best_method": fs.LSTM_METHOD, "mae_hw": 0.18, "mae_lstm": 0.17}
    fs.save_selection(path, payload)
    assert fs.load_selection(path) == payload


def test_load_selection_missing_returns_none(tmp_path):
    assert fs.load_selection(tmp_path / "nope.json") is None


def test_resolve_inference_with_onnx():
    assert fs.resolve_inference_method(
        {"best_method": fs.LSTM_METHOD}, onnx_available=True) == fs.ONNX_METHOD


def test_resolve_inference_no_onnx_falls_back():
    assert fs.resolve_inference_method(
        {"best_method": fs.LSTM_METHOD}, onnx_available=False) == fs.HW_METHOD


def test_resolve_inference_hw_selection():
    assert fs.resolve_inference_method(
        {"best_method": fs.HW_METHOD}, onnx_available=True) == fs.HW_METHOD


def test_resolve_inference_no_selection():
    assert fs.resolve_inference_method(None, onnx_available=True) == fs.HW_METHOD
