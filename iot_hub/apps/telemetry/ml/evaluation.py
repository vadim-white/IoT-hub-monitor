"""Оценка детекторов против ground-truth — чистый numpy, без Django.

Point-wise метрики (precision/recall/F1/false-alarm), recall в разрезе типа
аномалии и время до детекции. Точки warmup исключаются из всех знаменателей,
чтобы сравнение методов было честным независимо от размера окна.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .dataset import TimeSeries


@dataclass(frozen=True)
class PointMetrics:
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float
    recall: float
    f1: float
    false_alarm_rate: float   # fp / (fp + tn) — доля ложных тревог среди нормы
    support_pos: int          # ground-truth аномалий (вне warmup)
    n_evaluated: int          # точек учтено (всего минус warmup)


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def point_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    warmup_mask: np.ndarray | None = None,
) -> PointMetrics:
    """Point-wise метрики. warmup-точки исключаются из обеих сторон."""
    y_true = np.asarray(y_true, dtype=bool)
    y_pred = np.asarray(y_pred, dtype=bool)
    if warmup_mask is not None:
        keep = ~np.asarray(warmup_mask, dtype=bool)
        y_true, y_pred = y_true[keep], y_pred[keep]

    tp = int(np.sum(y_true & y_pred))
    fp = int(np.sum(~y_true & y_pred))
    fn = int(np.sum(y_true & ~y_pred))
    tn = int(np.sum(~y_true & ~y_pred))

    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    f1 = _safe_div(2 * precision * recall, precision + recall)
    far = _safe_div(fp, fp + tn)

    return PointMetrics(
        tp=tp, fp=fp, fn=fn, tn=tn,
        precision=precision, recall=recall, f1=f1, false_alarm_rate=far,
        support_pos=tp + fn, n_evaluated=tp + fp + fn + tn,
    )


def per_type_recall(
    series: TimeSeries,
    y_pred: np.ndarray,
    warmup_mask: np.ndarray | None = None,
) -> dict[str, float]:
    """Recall в разрезе anomaly_type (spike/drift/stuck/dropout/noise_burst).

    Показывает сильные/слабые стороны метода: z-score хорошо ловит spike и плохо
    stuck — это мотивирует переход к следующему методу.
    """
    if series.anomaly_types is None:
        return {}
    types = np.asarray(series.anomaly_types, dtype=object)
    y_pred = np.asarray(y_pred, dtype=bool)
    keep = np.ones(len(y_pred), dtype=bool)
    if warmup_mask is not None:
        keep = ~np.asarray(warmup_mask, dtype=bool)

    out: dict[str, float] = {}
    for atype in sorted({t for t in types if t}):
        mask = (types == atype) & keep
        total = int(mask.sum())
        if total:
            out[atype] = _safe_div(int((mask & y_pred).sum()), total)
    return out


def _segments(labels: np.ndarray) -> list[tuple[int, int]]:
    """Непрерывные сегменты True в bool-массиве → список (start, end_exclusive)."""
    labels = np.asarray(labels, dtype=bool)
    segs: list[tuple[int, int]] = []
    start = None
    for i, v in enumerate(labels):
        if v and start is None:
            start = i
        elif not v and start is not None:
            segs.append((start, i))
            start = None
    if start is not None:
        segs.append((start, len(labels)))
    return segs


def detection_latency(
    series: TimeSeries,
    y_pred: np.ndarray,
    warmup_mask: np.ndarray | None = None,
) -> dict:
    """Задержка детекции по эпизодам: для каждого ground-truth сегмента —
    смещение первой сработавшей точки от его начала (в точках). Пропущенные
    сегменты (не сработал ни разу) — в missed.

    warmup_mask в сигнатуре ради единообразия с остальными метриками, но не
    нужен: эпизоды аномалий в синтетике не попадают в warmup-зону начала ряда.
    """
    if series.labels is None:
        return {}
    y_pred = np.asarray(y_pred, dtype=bool)
    segs = _segments(series.labels)
    latencies: list[int] = []
    missed = 0
    for start, end in segs:
        fired = np.nonzero(y_pred[start:end])[0]
        if len(fired):
            latencies.append(int(fired[0]))
        else:
            missed += 1
    return {
        "episodes": len(segs),
        "detected": len(latencies),
        "missed": missed,
        "median_latency_points": float(np.median(latencies)) if latencies else None,
    }
