"""Персистентность обученных моделей ML-ядра (Фаза 4, инкремент 1).

Проблема: детекторы/форкастеры хранят обученное состояние только в памяти (поля
dataclass `_model`, `_stats`, ...), поэтому каждый запуск команды переобучает
модель с нуля. Для прода это абсурд (autoencoder — десятки секунд на прогон).

Решение: каждая модель получает save(stem)/load(stem) через ModelPersistenceMixin.
Артефакт = пара файлов под общим basename `stem`:
  <stem>.manifest.json  — {name, version, hyperparams, sha} (читается ВСЕГДА первым)
  <stem>.{pt|joblib|npz}— нативные веса (формат выбирает сам класс)

Контракт: после load(stem) объект даёт байт-в-байт те же score/predict/forecast,
что и после fit() при тех же гиперпараметрах и seed.

Торч-агностичность: этот модуль НЕ импортирует torch/joblib. Нативную часть
сериализации делает конкретный класс в _dump_state/_load_state, импортируя свои
зависимости локально — иначе прогон в .venv-analysis (без torch) упал бы на импорте.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import fields
from pathlib import Path

# Артефакты лежат рядом с ML-кодом: iot_hub/apps/telemetry/ml/models/.
# Путь от пакета, а не от Django settings, — ML-ядро про Django не знает.
ML_MODELS_DIR = Path(__file__).resolve().parent / "models"


class CacheMismatchError(Exception):
    """Гиперпараметры объекта не совпали с манифестом артефакта.

    Поднимается load() при расхождении sha. Сигнал «переобучи», а НЕ тихая
    загрузка несовместимых весов с неверным последующим скорингом.
    """


def model_dir() -> Path:
    """Каталог артефактов, создаётся при первом обращении."""
    ML_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    return ML_MODELS_DIR


def _slug(value) -> str:
    """Безопасный для имени файла фрагмент: всё кроме [A-Za-z0-9._-] → '-'."""
    s = "all" if value is None else str(value)
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-") or "all"


def model_key(name: str, device=None, metric=None) -> Path:
    """Детерминированный stem артефакта: <models>/<name>__<device>__<metric>."""
    stem = f"{_slug(name)}__{_slug(device)}__{_slug(metric)}"
    return model_dir() / stem


def hyperparams(model) -> dict:
    """Гиперпараметры модели = init-поля dataclass.

    Обученное состояние помечено field(init=False) и в хеш НЕ попадает —
    иначе sha зависел бы от данных обучения и инвалидация срабатывала бы всегда.
    """
    return {f.name: getattr(model, f.name) for f in fields(model) if f.init}


def _sha(params: dict, version: int) -> str:
    """sha256 от version + sorted-JSON гиперпараметров (стабилен между запусками)."""
    payload = json.dumps(
        {"version": version, "params": params},
        sort_keys=True,
        default=str,  # на случай не-JSON значений в гиперпараметрах
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ModelPersistenceMixin:
    """Шаблонные save/load: манифест+хеш здесь, нативные веса — в _dump_state/_load_state.

    Подмешивается ПЕРЕД ABC в списке баз (ModelPersistenceMixin, AnomalyDetector),
    полей не вносит — на dataclass-порядок аргументов не влияет.
    """

    PERSIST_VERSION = 1

    def manifest(self) -> dict:
        params = hyperparams(self)
        return {
            "name": getattr(self, "name", type(self).__name__),
            "version": self.PERSIST_VERSION,
            "hyperparams": params,
            "sha": _sha(params, self.PERSIST_VERSION),
        }

    def save(self, stem) -> Path:
        """Записать <stem>.manifest.json + нативные веса. Возвращает stem (Path)."""
        stem = Path(stem)
        stem.parent.mkdir(parents=True, exist_ok=True)
        man = self.manifest()
        self._dump_state(stem)
        stem.with_suffix(".manifest.json").write_text(
            json.dumps(man, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return stem

    def load(self, stem) -> "ModelPersistenceMixin":
        """Прочитать манифест, сверить sha с текущим объектом, восстановить веса.

        FileNotFoundError — если артефакта нет (cache miss).
        CacheMismatchError — если гиперпараметры не совпали (нужно переобучить).
        """
        stem = Path(stem)
        man_path = stem.with_suffix(".manifest.json")
        if not man_path.exists():
            raise FileNotFoundError(f"Манифест не найден: {man_path}")
        manifest = json.loads(man_path.read_text(encoding="utf-8"))
        current_sha = _sha(hyperparams(self), self.PERSIST_VERSION)
        if manifest.get("sha") != current_sha:
            raise CacheMismatchError(
                f"Гиперпараметры не совпали с артефактом {stem.name}: "
                f"манифест sha={manifest.get('sha')[:12]}…, текущий={current_sha[:12]}…"
            )
        self._load_state(stem, manifest)
        return self

    # --- точки расширения (реализует каждый класс) ---

    def _dump_state(self, stem: Path) -> None:
        raise NotImplementedError

    def _load_state(self, stem: Path, manifest: dict) -> None:
        raise NotImplementedError
