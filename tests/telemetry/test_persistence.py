"""Тесты персистентности ML-моделей (Фаза 4, инкремент 1).

Контракт: fit → save → новый объект тех же гиперпараметров → load даёт
байт-в-байт те же score/predict/forecast. Плюс манифест и инвалидация по sha.

torch-модели (autoencoder, lstm) гейтятся importorskip внутри своих секций;
IForest/HoltWinters — под sklearn/statsmodels. Целевой прогон — Docker.
"""
import numpy as np
import pytest

from iot_hub.apps.telemetry.ml.dataset import TimeSeries
from iot_hub.apps.telemetry.ml.persistence import (
    CacheMismatchError,
    hyperparams,
    model_key,
    _sha,
)


def _series(values, types=None):
    n = len(values)
    ts = np.datetime64("2025-01-01") + np.arange(n) * np.timedelta64(10, "m")
    labels = None
    if types is not None:
        labels = np.array([bool(t) for t in types], dtype=bool)
        types = np.array(types, dtype=object)
    return TimeSeries(timestamps=ts, values=np.asarray(values, float),
                      labels=labels, anomaly_types=types)


def _noisy(n=600, seed=0):
    return np.random.default_rng(seed).normal(50.0, 1.0, n)


# --- helpers общего модуля persistence ---

def test_model_key_deterministic_and_safe(tmp_path):
    k1 = model_key("iforest", "TEMP-001", "temperature")
    k2 = model_key("iforest", "TEMP-001", "temperature")
    assert k1 == k2
    # схема: <models>/<device>/<name>__<metric> — device задаёт подпапку
    assert k1.name == "iforest__temperature"
    assert k1.parent.name == "TEMP-001"
    # None → "all"; небезопасные символы → '-'
    k3 = model_key("zscore", None, "a/b c")
    assert k3.name == "zscore__a-b-c" and k3.parent.name == "all"


def test_sha_changes_with_params():
    a = _sha({"window": 24, "threshold": 3.0}, 1)
    b = _sha({"window": 48, "threshold": 3.0}, 1)
    c = _sha({"window": 24, "threshold": 3.0}, 1)
    assert a == c and a != b


# --- ZScore: stateless ---

def test_zscore_roundtrip_and_stateless(tmp_path):
    from iot_hub.apps.telemetry.ml.detectors.zscore import ZScoreDetector

    s = _series(_noisy())
    det = ZScoreDetector(window=24, threshold=3.0)
    before = det.predict(s)

    stem = tmp_path / "zscore__all__temp"
    det.save(stem)
    assert stem.with_suffix(".manifest.json").exists()
    # stateless: бинарного файла весов нет
    assert not (tmp_path / "zscore__all__temp.joblib").exists()

    restored = ZScoreDetector(window=24, threshold=3.0).load(stem)
    after = restored.predict(s)
    np.testing.assert_array_equal(before.scores, after.scores)
    np.testing.assert_array_equal(before.predictions, after.predictions)


# --- IsolationForest ---

def test_iforest_roundtrip_identity(tmp_path):
    pytest.importorskip("sklearn")
    from iot_hub.apps.telemetry.ml.detectors.iforest import IsolationForestDetector

    s = _series(_noisy())
    det = IsolationForestDetector(window=72, random_state=42).fit(s)
    before = det.predict(s)

    stem = model_key("iforest", "TEMP-001", "temperature")
    # перенаправим в tmp, чтобы не мусорить в реальном models/
    stem = tmp_path / stem.name
    det.save(stem)
    assert stem.with_suffix(".manifest.json").exists()
    assert (tmp_path / f"{stem.name}.joblib").exists()

    restored = IsolationForestDetector(window=72, random_state=42).load(stem)
    after = restored.predict(s)
    np.testing.assert_array_equal(before.scores, after.scores)
    np.testing.assert_array_equal(before.predictions, after.predictions)


def test_manifest_contents(tmp_path):
    pytest.importorskip("sklearn")
    from iot_hub.apps.telemetry.ml.detectors.iforest import IsolationForestDetector
    import json

    det = IsolationForestDetector(window=72).fit(_series(_noisy()))
    stem = tmp_path / "iforest__d__m"
    det.save(stem)
    man = json.loads(stem.with_suffix(".manifest.json").read_text())
    assert man["name"] == "iforest"
    assert man["version"] == 1
    assert man["hyperparams"]["window"] == 72
    assert man["sha"] == _sha(hyperparams(det), det.PERSIST_VERSION)


def test_invalidation_on_param_mismatch(tmp_path):
    pytest.importorskip("sklearn")
    from iot_hub.apps.telemetry.ml.detectors.iforest import IsolationForestDetector

    det = IsolationForestDetector(window=72).fit(_series(_noisy()))
    stem = tmp_path / "iforest__d__m"
    det.save(stem)
    # загрузка объектом с ДРУГИМ window → отказ, а не тихий неверный скоринг
    with pytest.raises(CacheMismatchError):
        IsolationForestDetector(window=48).load(stem)


def test_load_missing_artifact_raises(tmp_path):
    pytest.importorskip("sklearn")
    from iot_hub.apps.telemetry.ml.detectors.iforest import IsolationForestDetector

    with pytest.raises(FileNotFoundError):
        IsolationForestDetector(window=72).load(tmp_path / "nope")


# --- Autoencoder (torch) ---

def test_autoencoder_roundtrip_identity(tmp_path):
    pytest.importorskip("torch")
    from iot_hub.apps.telemetry.ml.detectors.autoencoder import AutoencoderDetector

    s = _series(_noisy(n=400))
    det = AutoencoderDetector(window=48, latent_dim=4, epochs=20, random_state=7).fit(s)
    before = det.predict(s)

    stem = tmp_path / "autoencoder__d__m"
    det.save(stem)
    assert (tmp_path / "autoencoder__d__m.pt").exists()

    restored = AutoencoderDetector(window=48, latent_dim=4, epochs=20,
                                   random_state=7).load(stem)
    after = restored.predict(s)
    np.testing.assert_allclose(before.scores, after.scores, rtol=1e-5, atol=1e-6)
    np.testing.assert_array_equal(before.predictions, after.predictions)


# --- forecasters ---

def _fc_series(n=900, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    vals = 50 + 5 * np.sin(2 * np.pi * t / 144) + rng.normal(0, 0.5, n)
    return _series(vals)


def test_naive_roundtrip_identity(tmp_path):
    from iot_hub.apps.telemetry.ml.forecasters.naive import SeasonalNaiveForecaster

    s = _fc_series()
    f = SeasonalNaiveForecaster(seasonal_periods=144).fit(s)
    before = f.forecast(36)
    stem = tmp_path / "naive__d__m"
    f.save(stem)

    after = SeasonalNaiveForecaster(seasonal_periods=144).load(stem).forecast(36)
    np.testing.assert_array_equal(before.mean, after.mean)
    np.testing.assert_array_equal(before.timestamps, after.timestamps)


def test_holtwinters_roundtrip_identity(tmp_path):
    pytest.importorskip("statsmodels")
    from iot_hub.apps.telemetry.ml.forecasters.holtwinters import HoltWintersForecaster

    s = _fc_series()
    f = HoltWintersForecaster(seasonal_periods=144).fit(s)
    before = f.forecast(36)
    stem = tmp_path / "hw__d__m"
    f.save(stem)

    after = HoltWintersForecaster(seasonal_periods=144).load(stem).forecast(36)
    np.testing.assert_allclose(before.mean, after.mean, rtol=1e-9, atol=1e-9)


def test_lstm_roundtrip_both_paths(tmp_path):
    """LSTM строит сеть лениво на первом forecast. save/load обязан работать
    и ДО первого forecast (_model is None), и ПОСЛЕ (сеть обучена)."""
    pytest.importorskip("torch")
    from iot_hub.apps.telemetry.ml.forecasters.lstm import LSTMForecaster

    s = _fc_series(n=600)

    # путь 1: save сразу после fit (модель ещё не построена)
    f1 = LSTMForecaster(window=72, epochs=10, hidden=8, random_state=7).fit(s)
    assert f1._model is None
    f1.save(tmp_path / "lstm_pre")
    assert not (tmp_path / "lstm_pre.pt").exists()  # весов сети ещё нет
    restored_pre = LSTMForecaster(window=72, epochs=10, hidden=8,
                                  random_state=7).load(tmp_path / "lstm_pre")
    # после load lazy-build обучает сеть детерминированно (тот же seed)
    expected = LSTMForecaster(window=72, epochs=10, hidden=8, random_state=7).fit(s).forecast(24)
    np.testing.assert_allclose(restored_pre.forecast(24).mean, expected.mean,
                               rtol=1e-5, atol=1e-5)

    # путь 2: save ПОСЛЕ forecast (сеть обучена, веса сохранены)
    f2 = LSTMForecaster(window=72, epochs=10, hidden=8, random_state=7).fit(s)
    before = f2.forecast(24)
    assert f2._model is not None
    f2.save(tmp_path / "lstm_post")
    assert (tmp_path / "lstm_post.pt").exists()
    restored_post = LSTMForecaster(window=72, epochs=10, hidden=8,
                                   random_state=7).load(tmp_path / "lstm_post")
    after = restored_post.forecast(24)  # тот же horizon → НЕ переобучает
    np.testing.assert_allclose(before.mean, after.mean, rtol=1e-6, atol=1e-6)
