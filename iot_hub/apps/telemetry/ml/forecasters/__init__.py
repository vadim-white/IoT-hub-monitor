"""Реестр прогнозистов. Новый метод = новый файл + одна строка в FORECASTER_REGISTRY.

naive — на голом numpy, всегда доступен. holtwinters (statsmodels) и lstm (torch)
регистрируются через try/except: в окружениях без зависимости метод недоступен,
но naive продолжает работать.
"""
from __future__ import annotations

from ..forecast_base import Forecaster
from .naive import SeasonalNaiveForecaster

FORECASTER_REGISTRY: dict[str, type[Forecaster]] = {
    "naive": SeasonalNaiveForecaster,
}

try:
    from .holtwinters import HoltWintersForecaster
    FORECASTER_REGISTRY["holtwinters"] = HoltWintersForecaster
except ImportError:
    pass

try:
    from .lstm import LSTMForecaster
    FORECASTER_REGISTRY["lstm"] = LSTMForecaster
except ImportError:
    pass

# lstm_lf_resid требует и torch, и statsmodels (внутренний HW) — оба под try/except
try:
    from .lstm_level_fix_residual import LSTMLevelFixResidualForecaster
    FORECASTER_REGISTRY["lstm_lf_resid"] = LSTMLevelFixResidualForecaster
except ImportError:
    pass

# lstm_lf_resid_onnx — боевой инференс без torch (onnxruntime + statsmodels для HW).
# Доступен на проде, где torch не нужен; обучение/экспорт .onnx — у lstm_lf_resid.
try:
    from .lstm_lf_resid_onnx import LSTMLfResidOnnxForecaster
    FORECASTER_REGISTRY["lstm_lf_resid_onnx"] = LSTMLfResidOnnxForecaster
except ImportError:
    pass


def build_forecaster(method: str, **params) -> Forecaster:
    if method not in FORECASTER_REGISTRY:
        raise ValueError(
            f"Неизвестный метод '{method}'. Доступны: {list(FORECASTER_REGISTRY)}")
    return FORECASTER_REGISTRY[method](**params)
