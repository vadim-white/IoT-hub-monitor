"""Реестр детекторов. Новый метод = новый файл + одна строка в DETECTOR_REGISTRY."""
from __future__ import annotations

from ..base import AnomalyDetector
from .zscore import ZScoreDetector
from .iforest import IsolationForestDetector

DETECTOR_REGISTRY: dict[str, type[AnomalyDetector]] = {
    "zscore": ZScoreDetector,
    "iforest": IsolationForestDetector,
    # "autoencoder": AutoencoderDetector,   # инкремент 3 (torch)
}


def build_detector(method: str, **params) -> AnomalyDetector:
    if method not in DETECTOR_REGISTRY:
        raise ValueError(
            f"Неизвестный метод '{method}'. Доступны: {list(DETECTOR_REGISTRY)}")
    return DETECTOR_REGISTRY[method](**params)
