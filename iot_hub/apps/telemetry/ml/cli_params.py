"""Единый источник правды для гиперпараметров из CLI-опций команд.

detect_anomalies, forecast_telemetry и train_models строят модели из одних и тех
же --флагов. Чтобы кэш (persistence) совпадал по sha между «обучить» и «скорить»,
гиперпараметры обязаны собираться идентично — поэтому логика здесь, в одном месте.
"""
from __future__ import annotations

# lstm_lf_resid — «модель победителя» (Фаза 5, раунд 4): гиперпараметры зафиксированы
# и НЕ берутся из общих --window/--epochs/--hidden (у train_models их дефолты заточены
# под autoencoder: window=24, epochs=150). Жёсткая фиксация гарантирует, что Colab-веса
# и локальный --use-cache всегда совпадают по sha без необходимости дублировать флаги.
LSTM_LF_RESID_DEFAULTS = {
    "window": 144, "epochs": 100, "lr": 1e-3, "hidden": 32,
    "seasonal_periods": 144, "random_state": 42,
}


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
    if method == "lstm_lf_resid":
        # ВСЕ гиперпараметры фиксированы (включая random_state) — НЕ из общих CLI-флагов.
        # Это «модель победителя»: полностью детерминирована, sha артефакта стабилен между
        # Colab-обучением и локальным --use-cache независимо от --window/--epochs/--random-state.
        return dict(LSTM_LF_RESID_DEFAULTS)
    return {}
