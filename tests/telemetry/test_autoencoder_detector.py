"""Тесты AutoencoderDetector. Требуют torch — пропускаются, если его нет
(напр. в .venv-analysis); целевой прогон в Docker."""
import numpy as np
import pytest

pytest.importorskip("torch")

from iot_hub.apps.telemetry.ml.dataset import TimeSeries
from iot_hub.apps.telemetry.ml.detectors.autoencoder import AutoencoderDetector
from iot_hub.apps.telemetry.ml.detectors.zscore import ZScoreDetector
from iot_hub.apps.telemetry.ml.evaluation import per_type_recall


def _oscillating(n=1500, period=48, amp=5.0, noise=0.5, seed=0):
    """Осциллирующая норма: AE учит синус, плато на нём — явная аномалия формы.
    На чистом гауссовом шуме у AE нет динамики для нарушения — тест был бы слабым."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    return 50.0 + amp * np.sin(2 * np.pi * t / period) + rng.normal(0, noise, n)


def _series(values, types=None):
    n = len(values)
    ts = np.datetime64("2025-01-01") + np.arange(n) * np.timedelta64(10, "m")
    labels = None
    if types is not None:
        labels = np.array([bool(t) for t in types], dtype=bool)
        types = np.array(types, dtype=object)
    return TimeSeries(timestamps=ts, values=values.astype(float),
                      labels=labels, anomaly_types=types)


def test_fits_interface():
    res = AutoencoderDetector(window=72, epochs=10).predict(_series(_oscillating()))
    n = 1500
    assert res.scores.shape == (n,)
    assert res.predictions.shape == (n,)
    assert res.warmup_mask.shape == (n,)


def test_deterministic():
    s = _series(_oscillating())
    r1 = AutoencoderDetector(window=72, epochs=10, random_state=42).predict(s)
    r2 = AutoencoderDetector(window=72, epochs=10, random_state=42).predict(s)
    np.testing.assert_array_equal(r1.scores, r2.scores)
    np.testing.assert_array_equal(r1.predictions, r2.predictions)


def test_warmup_never_predicts():
    res = AutoencoderDetector(window=72, epochs=10).predict(_series(_oscillating()))
    assert res.warmup_mask[:71].all()           # window-1 точек без полного окна
    assert not res.predictions[res.warmup_mask].any()


def test_meta_has_threshold_key():
    res = AutoencoderDetector(window=72, epochs=10).predict(_series(_oscillating()))
    assert "threshold" in res.meta["params"]
    assert np.isfinite(res.meta["params"]["threshold"])
    assert res.meta["method"] == "autoencoder"


def test_causality_no_lookahead():
    """Изменение далёкой точки не влияет на score точек левее (нет look-ahead)."""
    values = _oscillating()
    s1 = _series(values.copy())
    det = AutoencoderDetector(window=72, epochs=10, random_state=42)
    base = det.fit(s1).score(s1)
    # та же обученная модель на изменённом ряде — окна левее t=1000 не видят t=1000
    spiked = values.copy()
    spiked[1000] += 50.0
    after = det.score(_series(spiked))
    np.testing.assert_array_equal(base[:1000], after[:1000])


def test_catches_stuck_better_than_baselines():
    """Главный научный тест: автоэнкодер ловит залипание (stuck), которого не
    берут ни z-score, ни Isolation Forest.

    Норма — осцилляция (синус+шум). Stuck-плато длиннее окна: AE, выучив форму
    синуса, реконструирует застывший участок с растущей ошибкой.
    """
    values = _oscillating(n=1500, seed=0)
    types = [""] * 1500
    values[700:800] = values[700]  # плато 100 точек > окна 72
    for i in range(700, 800):
        types[i] = "stuck"
    s = _series(values, types)

    ae = AutoencoderDetector(window=72, epochs=80, latent_dim=4,
                             threshold_percentile=90.0, random_state=42).predict(s)
    zs = ZScoreDetector(window=72, threshold=3.0).predict(s)

    ae_recall = per_type_recall(s, ae.predictions, ae.warmup_mask).get("stuck", 0.0)
    zs_recall = per_type_recall(s, zs.predictions, zs.warmup_mask).get("stuck", 0.0)

    assert zs_recall == 0.0, "z-score структурно слеп к stuck"
    assert ae_recall > 0.5, "AE должен поймать большую часть stuck-сегмента"

    sklearn = pytest.importorskip("sklearn")  # noqa: F841
    from iot_hub.apps.telemetry.ml.detectors.iforest import IsolationForestDetector
    if_pred = IsolationForestDetector(window=72, contamination=0.05).predict(s)
    if_recall = per_type_recall(s, if_pred.predictions, if_pred.warmup_mask).get("stuck", 0.0)
    assert ae_recall >= if_recall, "AE должен брать stuck не хуже Isolation Forest"


def test_normal_no_anomaly_low_far():
    """На чистом осциллирующем ряде без аномалий доля сработок мала (sanity)."""
    res = AutoencoderDetector(window=72, epochs=40, threshold_percentile=98.0,
                              random_state=42).predict(_series(_oscillating()))
    far = res.predictions.sum() / (~res.warmup_mask).sum()
    assert far < 0.05
