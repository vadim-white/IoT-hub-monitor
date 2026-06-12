"""Torch-специфика автоэнкодера, изолированная в одном модуле.

Здесь единственное место `import torch` в ML-ядре — остальной код (реестр,
команда) не тянет torch, пока явно не запрошен метод autoencoder. Содержит:
детерминизм, построение каузальных окон, нормализацию и саму сеть.
"""
from __future__ import annotations

import numpy as np
import torch
from torch import nn


def set_torch_determinism(seed: int) -> None:
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)


def make_causal_windows(values: np.ndarray, window: int) -> tuple[np.ndarray, np.ndarray]:
    """W[t] = x[t-window+1 : t+1] — прошлое ВКЛЮЧАЯ текущую точку t (causal, без будущего).

    Важно: окно содержит саму точку t. Иначе аномалия в t не влияет на реконструкцию
    её собственного окна, и point-wise оценка засчитывает её только со сдвигом — что
    нечестно по сравнению с z-score/IF, которые «видят» value[t] напрямую.
    Первые window-1 точек — warmup (нет полного окна).
    """
    x = np.asarray(values, dtype=float)
    n = len(x)
    W = np.zeros((n, window), dtype=np.float32)
    warmup = np.zeros(n, dtype=bool)
    warmup[: window - 1] = True
    if n >= window:
        # sliding_window_view(x, window)[i] = x[i:i+window] → присваиваем точке t=i+window-1
        W[window - 1:] = np.lib.stride_tricks.sliding_window_view(x, window)
    return W, warmup


def global_standardize(W: np.ndarray, stats: tuple[float, float] | None = None
                       ) -> tuple[np.ndarray, tuple[float, float]]:
    """Глобальная стандартизация: (W - mean) / std по ОДНОЙ паре скаляров на весь
    train. stats вычисляются на train, переиспользуются на score без утечки.

    ВАЖНО: НЕ per-window centering (вычитание среднего окна) — оно превращает
    залипшее плато в нулевой вектор, который автоэнкодер реконструирует идеально,
    то есть маскирует stuck. Глобальные mean/std сохраняют абсолютный уровень,
    поэтому обрыв динамики в плато остаётся аномальной формой.
    """
    if stats is None:
        stats = (float(W.mean()), float(W.std()) + 1e-9)
    mean, std = stats
    return ((W - mean) / std).astype(np.float32), stats


class MLPAutoencoder(nn.Module):
    """Undercomplete MLP-автоэнкодер: window → hidden → latent → hidden → window.

    Bottleneck latent << window заставляет учить компактное представление
    нормальной формы окна; аномальная форма (обрыв в плато) реконструируется плохо.
    Маленькая сеть — обучение секунды на CPU, инференс мгновенный, edge-friendly.
    """
    def __init__(self, window: int, latent_dim: int):
        super().__init__()
        hidden = max(latent_dim, window // 2)
        self.encoder = nn.Sequential(
            nn.Linear(window, hidden), nn.ReLU(),
            nn.Linear(hidden, latent_dim), nn.ReLU(),
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, hidden), nn.ReLU(),
            nn.Linear(hidden, window),
        )

    def forward(self, x):
        return self.decoder(self.encoder(x))
