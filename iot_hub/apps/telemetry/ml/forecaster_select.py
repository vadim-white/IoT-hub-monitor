"""Авто-выбор форкастера HW vs LSTM lf-resid (Фаза 4, инкр. 6–7).

Гибрид «оценка ↔ инференс», но БЕЗ переобучения (инкр.7):
  • ОЦЕНКА — сравнение ГОТОВЫХ весов на hold-out отрезке: HW (переобучается на срезе,
    statsmodels, без torch) и LSTM (готовый ONNX через forecast_from, без torch)
    прогнозируют hold-out → MAE → выбор лучшего. НИКАКОГО fit() LSTM.
  • ИНФЕРЕНС — читает выбор и прогнозирует выбранным методом.

Зачем без переобучения: rolling-origin backtest с fit() тянет torch и грузит CPU →
противоречит «обучение LSTM только в Colab» и «Render без torch». Оценка готовых весов
на hold-out выполнима НА RENDER (onnxruntime + statsmodels, без torch) → выбор честен
по ФАКТИЧЕСКОМУ ряду Render (решает «Render-ряд ≠ ряд обучения»).

Честность: на TEMP-004 LSTM проигрывает HW — авто-выбор обязан выбрать HW (LSTM берём
только если СТРОГО лучше). Это доказательство, что отбор не подкручен под LSTM.

Формат артефакта <stem>_forecaster_select.json (без sha-инвалидации — это метаданные
решения, не веса):
  {"best_method", "mae_hw", "mae_lstm", "holdout", "horizon", "eval", "evaluated_at"}
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .forecasters import build_forecaster
from .forecast_evaluation import forecast_point_metrics, slice_series
from .persistence import CacheMismatchError, model_key

# базовые форкастеры авто-выбора: лёгкий боевой HW vs LSTM-победитель Фазы 5
HW_METHOD = "holtwinters"
LSTM_METHOD = "lstm_lf_resid"
ONNX_METHOD = "lstm_lf_resid_onnx"

SELECT_SUFFIX = "_forecaster_select.json"


def selection_key(device_sn, metric_type) -> Path:
    """Путь к JSON-выбору рядом с весами: <models>/<sn>__<metric>__..._forecaster_select.json.

    Привязан к stem весов lstm_lf_resid через model_key — выбор и артефакт LSTM
    лежат одним «комплектом» (вместе кладутся на Render Shell)."""
    stem = model_key(LSTM_METHOD, device_sn, metric_type)
    return stem.with_name(stem.name + SELECT_SUFFIX)


def evaluate_and_select(
    series, *, device_sn, metric_type, horizon: int, holdout: int | None = None,
    seasonal_periods: int = 144,
) -> dict:
    """Оценка ГОТОВЫХ весов HW vs LSTM на hold-out, выбор лучшего по MAE (инкр.7).

    БЕЗ переобучения LSTM (только готовый ONNX) → выполнимо на Render без torch.
    hold-out = последние `holdout` точек (дефолт = horizon). HW переобучается на
    срезе series[:cut] (statsmodels, без torch), LSTM прогнозирует от того же среза
    через forecast_from готовой ONNX-модели.

    Прогноз всегда строится на `horizon` точек (ONNX-граф зашит под него), но MAE
    считается на пересечении `eval_len = min(holdout, horizon)` — иначе при
    holdout != horizon длины truth и прогноза разойдутся.

    LSTM выбираем ТОЛЬКО если строго лучше HW (равенство/ошибка/нет .onnx → HW).
    """
    holdout = holdout or horizon
    n = len(series.values)
    cut = n - holdout
    eval_len = min(holdout, horizon)
    if cut < 1:
        # ряд короче, чем нужно для hold-out → честно остаёмся на HW
        return _payload(HW_METHOD, None, None, holdout, horizon)

    truth = series.values[cut:cut + eval_len]
    past = slice_series(series, cut)

    # HW: переобучаем на срезе (лёгко, без torch) → прогноз hold-out
    mae_hw = None
    try:
        hw = build_forecaster(HW_METHOD, seasonal_periods=seasonal_periods).fit(past)
        mae_hw, _, _ = forecast_point_metrics(truth, hw.forecast(horizon).mean[:eval_len])
    except Exception:
        mae_hw = None

    # LSTM: готовый ONNX, прогноз от конца среза (forecast_from), без torch
    mae_lstm = None
    onnx = _load_onnx(device_sn, metric_type, seasonal_periods)
    if onnx is not None:
        try:
            fc = onnx.forecast_from(past, horizon)
            mae_lstm, _, _ = forecast_point_metrics(truth, fc.mean[:eval_len])
        except Exception:
            mae_lstm = None

    best = HW_METHOD
    if mae_lstm is not None and (mae_hw is None or mae_lstm < mae_hw):
        best = LSTM_METHOD
    return _payload(best, mae_hw, mae_lstm, holdout, horizon)


def _load_onnx(device_sn, metric_type, seasonal_periods):
    """Загрузить готовый ONNX-форкастер для устройства/метрики; None — если нет/несовместим."""
    if not onnx_available(device_sn, metric_type):
        return None
    from .forecasters.lstm_lf_resid_onnx import LSTMLfResidOnnxForecaster

    stem = model_key(LSTM_METHOD, device_sn, metric_type)
    try:
        m = LSTMLfResidOnnxForecaster(seasonal_periods=seasonal_periods)
        m.load(stem)
        return m
    except (FileNotFoundError, CacheMismatchError):
        return None


def _payload(best, mae_hw, mae_lstm, holdout, horizon) -> dict:
    return {
        "best_method": best,
        "mae_hw": None if mae_hw is None else round(float(mae_hw), 4),
        "mae_lstm": None if mae_lstm is None else round(float(mae_lstm), 4),
        "holdout": holdout,
        "horizon": horizon,
        "eval": "holdout_ready_weights",
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def save_selection(path: Path, payload: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_selection(path: Path) -> dict | None:
    """Прочитать выбор; None — если файла нет (auto тогда → HW fallback)."""
    path = Path(path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def onnx_available(device_sn, metric_type) -> bool:
    """Есть ли .onnx-веса lstm_lf_resid для устройства/метрики (без torch-импорта)."""
    stem = model_key(LSTM_METHOD, device_sn, metric_type)
    return stem.with_suffix(".onnx").exists()


def resolve_inference_method(selection: dict | None, *, onnx_available: bool) -> str:
    """Метод для боевого инференса (без torch).

    LSTM выбран И .onnx есть → lstm_lf_resid_onnx; иначе holtwinters (тихий fallback).
    selection=None (нет файла) → holtwinters.
    """
    if selection and selection.get("best_method") == LSTM_METHOD and onnx_available:
        return ONNX_METHOD
    return HW_METHOD
