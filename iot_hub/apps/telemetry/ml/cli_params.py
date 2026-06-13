"""Единый источник правды для гиперпараметров из CLI-опций команд.

detect_anomalies, forecast_telemetry и train_models строят модели из одних и тех
же --флагов. Чтобы кэш (persistence) совпадал по sha между «обучить» и «скорить»,
гиперпараметры обязаны собираться идентично — поэтому логика здесь, в одном месте.
"""
from __future__ import annotations


def detector_params(method: str, opts: dict) -> dict:
    """Гиперпараметры детектора из opts по образцу detect_anomalies."""
    params = {"window": opts["window"], "threshold": opts["threshold"]}
    if method == "iforest":
        params.update(
            contamination=opts["contamination"],
            n_estimators=opts["n_estimators"],
            random_state=opts["random_state"],
        )
    elif method == "autoencoder":
        # AE калибрует порог по перцентилю; дефолт --threshold 3.0 не подходит
        params.pop("threshold", None)
        params.update(
            epochs=opts["epochs"],
            latent_dim=opts["latent_dim"],
            lr=opts["lr"],
            threshold_percentile=opts["threshold_percentile"],
            random_state=opts["random_state"],
        )
    return params


def forecaster_params(method: str, opts: dict) -> dict:
    """Гиперпараметры прогнозиста из opts по образцу forecast_telemetry."""
    if method in ("naive", "holtwinters"):
        return {"seasonal_periods": opts["seasonal_periods"]}
    if method == "lstm":
        return {
            "window": opts["window"], "epochs": opts["epochs"],
            "lr": opts["lr"], "hidden": opts["hidden"],
            "random_state": opts["random_state"],
        }
    return {}
