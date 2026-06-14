"""Тесты LSTMLevelFixResidualForecaster (Фаза 4, инкр. 4).

Гибрид HW + level-fix LSTM на остатке. Требует torch И statsmodels (внутренний HW) —
пропускается без любого из них. Целевой прогон — Docker.
"""
import numpy as np
import pytest

pytest.importorskip("torch")
pytest.importorskip("statsmodels")

from iot_hub.apps.telemetry.ml.dataset import TimeSeries
from iot_hub.apps.telemetry.ml.forecasters import build_forecaster
from iot_hub.apps.telemetry.ml.forecasters.lstm_level_fix_residual import (
    LSTMLevelFixResidualForecaster,
)
from iot_hub.apps.telemetry.ml.forecasters.naive import SeasonalNaiveForecaster
from iot_hub.apps.telemetry.ml.persistence import CacheMismatchError


def _series(values: np.ndarray) -> TimeSeries:
    n = len(values)
    ts = np.datetime64("2025-01-01") + np.arange(n) * np.timedelta64(10, "m")
    return TimeSeries(timestamps=ts, values=values.astype(float))


def _trend_season(n=900, period=144, seed=0):
    """Тренд + суточная сезонность + шум — близко к боевому temperature-ряду."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    return (50 + 0.002 * t + 5 * np.sin(2 * np.pi * t / period)
            + rng.normal(0, 0.4, n))


# гиперпараметры для быстрых тестов (window=period, чтобы окно ловило сезон)
_OPTS = dict(window=144, epochs=12, hidden=8, seasonal_periods=144, random_state=7)


def test_forecast_shape():
    fc = LSTMLevelFixResidualForecaster(**_OPTS).fit(_series(_trend_season())).forecast(36)
    assert fc.mean.shape == (36,)
    assert fc.horizon == 36
    assert fc.meta["method"] == "lstm_lf_resid"


def test_timestamps_continue():
    s = _series(_trend_season())
    fc = LSTMLevelFixResidualForecaster(**_OPTS).fit(s).forecast(6)
    assert fc.timestamps[0] == s.timestamps[-1] + np.timedelta64(10, "m")
    assert len(fc.timestamps) == 6


def test_deterministic():
    s = _series(_trend_season())
    r1 = LSTMLevelFixResidualForecaster(**_OPTS).fit(s).forecast(24)
    r2 = LSTMLevelFixResidualForecaster(**_OPTS).fit(s).forecast(24)
    np.testing.assert_allclose(r1.mean, r2.mean, rtol=1e-5, atol=1e-5)


def test_forecast_better_than_naive():
    """Smoke: гибрид разумнее seasonal-naive (не проверяем победу над HW —
    это задача диагностики, тут лишь sanity-check корректности реализации)."""
    full = _trend_season(n=900)
    train, test = full[:-36], full[-36:]
    s = _series(train)
    horizon = 36

    lf = LSTMLevelFixResidualForecaster(**_OPTS).fit(s).forecast(horizon).mean
    nv = SeasonalNaiveForecaster(seasonal_periods=144).fit(s).forecast(horizon).mean

    mae_lf = np.mean(np.abs(lf - test))
    mae_nv = np.mean(np.abs(nv - test))
    assert mae_lf < mae_nv


def test_registered_in_build_forecaster():
    model = build_forecaster("lstm_lf_resid", **_OPTS)
    assert isinstance(model, LSTMLevelFixResidualForecaster)


def test_persistence_roundtrip(tmp_path):
    """fit → forecast → save → load → forecast даёт идентичный вывод (сеть обучена)."""
    s = _series(_trend_season())
    f = LSTMLevelFixResidualForecaster(**_OPTS).fit(s)
    before = f.forecast(24)
    assert f._model is not None

    stem = tmp_path / "lf_resid__d__m"
    f.save(stem)
    assert (tmp_path / "lf_resid__d__m.pt").exists()
    assert (tmp_path / "lf_resid__d__m_hw.joblib").exists()  # артефакт внутреннего HW

    restored = LSTMLevelFixResidualForecaster(**_OPTS).load(stem)
    after = restored.forecast(24)  # тот же horizon → не переобучает
    np.testing.assert_allclose(before.mean, after.mean, rtol=1e-5, atol=1e-6)


def test_persistence_before_first_forecast(tmp_path):
    """save/load ДО первого forecast (_model is None) не падает; после load
    ленивое обучение детерминировано и совпадает с прямым fit→forecast."""
    s = _series(_trend_season())
    f = LSTMLevelFixResidualForecaster(**_OPTS).fit(s)
    assert f._model is None  # сеть ещё не построена

    stem = tmp_path / "lf_resid_pre"
    f.save(stem)
    assert not (tmp_path / "lf_resid_pre.pt").exists()  # весов сети ещё нет

    restored = LSTMLevelFixResidualForecaster(**_OPTS).load(stem)
    expected = LSTMLevelFixResidualForecaster(**_OPTS).fit(s).forecast(24)
    np.testing.assert_allclose(restored.forecast(24).mean, expected.mean,
                               rtol=1e-5, atol=1e-5)


def test_cache_invalidation(tmp_path):
    """load объектом с другим window → CacheMismatchError, а не тихий неверный вывод."""
    s = _series(_trend_season())
    f = LSTMLevelFixResidualForecaster(**_OPTS).fit(s)
    stem = tmp_path / "lf_resid__d__m"
    f.save(stem)

    bad_opts = {**_OPTS, "window": 72}
    with pytest.raises(CacheMismatchError):
        LSTMLevelFixResidualForecaster(**bad_opts).load(stem)
