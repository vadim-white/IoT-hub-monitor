"""ONNX-инференс LSTM level-fix на остатке HW — боевой прогнозист без torch (Фаза 4, инкр. 5).

Пара к `lstm_level_fix_residual.py`: тот класс ОБУЧАЕТ (torch, в Colab GPU / локально),
этот — ИНФЕРИТ из готовых артефактов через `onnxruntime`, БЕЗ torch. Реализует нарратив
диплома «train once, deploy anywhere»: тяжёлый LSTM учится один раз, а прод (мак/Render)
крутит инференс на лёгком onnxruntime, одинаково на любом железе (GPU-веса = CPU-вывод).

Читает те же артефакты, что пишет save() торч-класса:
  <stem>.onnx       — сеть приращений остатка (export_onnx торч-класса)
  <stem>.npz        — скаляры нормировки, хвост, шаг, горизонт
  <stem>_hw.joblib  — обученный Holt-Winters (скелет тренд+сезон)

Мат-аппарат прогноза 1-в-1 повторяет торч-класс:
  forecast = hw.forecast(h) + r_level + lstm_resid_increments * std

ВАЖНО (sha-совместимость): init-поля и `name` ДОЛЖНЫ совпадать с
LSTMLevelFixResidualForecaster — load() сверяет sha манифеста с гиперпараметрами
объекта, а манифест писал торч-класс. Поэтому `name = "lstm_lf_resid"` (не *_onnx);
в реестре форкастеров ключ другой ("lstm_lf_resid_onnx"), а метку метода берём из
`name` + суффикса в meta.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..dataset import TimeSeries
from ..forecast_base import Forecaster, ForecastResult, future_timestamps
from ..persistence import ModelPersistenceMixin
from .holtwinters import HoltWintersForecaster


@dataclass
class LSTMLfResidOnnxForecaster(ModelPersistenceMixin, Forecaster):
    # init-поля = поля торч-класса (тот же порядок и дефолты) → sha манифеста совпадает,
    # ONNX-класс принимает артефакт, обученный LSTMLevelFixResidualForecaster.
    window: int = 144
    epochs: int = 100
    lr: float = 1e-3
    hidden: int = 32
    seasonal_periods: int = 144
    random_state: int = 42
    name: str = "lstm_lf_resid"  # см. докстринг: совпадает с торч-классом ради sha
    # без аннотации типа → dataclass НЕ делает это полем (иначе попало бы в sha и сломало
    # совместимость артефакта с торч-классом). Просто override класс-атрибута Forecaster.
    inference_only = True  # только load+forecast; backtest (fit на origin) пропускается
    _hw: HoltWintersForecaster = field(default=None, init=False, repr=False)
    _session: object = field(default=None, init=False, repr=False)  # onnxruntime.InferenceSession
    _std: float = field(default=None, init=False, repr=False)
    _r_level: float = field(default=None, init=False, repr=False)
    _tail: np.ndarray = field(default=None, init=False, repr=False)
    _last_ts: np.datetime64 = field(default=None, init=False, repr=False)
    _step: np.timedelta64 = field(default=None, init=False, repr=False)
    _horizon: int = field(default=None, init=False, repr=False)  # зашит в граф ONNX

    def fit(self, series: TimeSeries) -> "LSTMLfResidOnnxForecaster":
        raise NotImplementedError(
            "LSTMLfResidOnnxForecaster — только инференс. Обучай "
            "LSTMLevelFixResidualForecaster (torch), экспортируй .onnx (export_onnx / "
            "команда export_onnx_models), затем грузи этот класс через load().")

    def forecast(self, horizon: int) -> ForecastResult:
        if self._hw is None:
            raise ValueError("Модель не загружена: вызови load(stem) перед forecast()")
        hw_fc = np.asarray(self._hw.forecast(horizon).mean, dtype=float)
        if self._session is None:
            # ряд был короче окна+горизонта на обучении → коррекции остатка нет, чистый HW
            mean = hw_fc
        else:
            if horizon != self._horizon:
                raise ValueError(
                    f"Горизонт зашит в ONNX-граф: обучено под {self._horizon}, "
                    f"запрошено {horizon}. Переэкспортируй .onnx под нужный горизонт.")
            x = np.asarray(self._tail, dtype=np.float32).reshape(1, self.window, 1)
            d = self._session.run(None, {"window": x})[0].ravel()
            resid_fc = self._r_level + d * self._std
            mean = hw_fc + resid_fc[:horizon]

        ts = future_timestamps(self._last_ts, self._step, horizon)
        return ForecastResult(
            timestamps=ts, mean=mean, lower=None, upper=None, horizon=horizon,
            meta={"method": "lstm_lf_resid_onnx", "seasonal_periods": self.seasonal_periods,
                  "params": {"window": self.window, "hidden": self.hidden,
                             "random_state": self.random_state}},
        )

    # --- персистентность: только load (обучение/dump — у торч-класса) ---
    def _dump_state(self, stem) -> None:
        raise NotImplementedError(
            "ONNX-класс не сохраняет состояние: артефакты пишет save()/export_onnx() "
            "торч-класса LSTMLevelFixResidualForecaster.")

    def _load_state(self, stem, manifest) -> None:
        import onnxruntime as ort
        from pathlib import Path

        stem = Path(stem)
        self._hw = HoltWintersForecaster(seasonal_periods=self.seasonal_periods).load(
            stem.with_name(stem.name + "_hw"))
        z = np.load(f"{stem}.npz", allow_pickle=False)
        self._std = float(z["std"])
        self._r_level = float(z["r_level"])
        self._tail = z["tail"]
        self._last_ts = z["last_ts"][()]
        self._step = z["step"][()]
        if bool(z["has_model"]):
            self._horizon = int(z["horizon"])
            onnx_path = f"{stem}.onnx"
            if not Path(onnx_path).exists():
                raise FileNotFoundError(
                    f"ONNX-веса не найдены: {onnx_path}. Запусти export_onnx_models "
                    "(или export_onnx() в Colab) для этого устройства/метрики.")
            self._session = ort.InferenceSession(
                onnx_path, providers=["CPUExecutionProvider"])
