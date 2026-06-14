# ML-тетрадки в Google Colab

Две группы: **обучение моделей** (Фаза 4, инкр. 2, ниже) и **диагностика сложных моделей**
(Фаза 5, в конце файла).

## Обучение ML-моделей в Colab (Фаза 4, инкремент 2)

Тяжёлые модели (автоэнкодер, LSTM) обучаются **централизованно в Colab**, а не на
ноутбуке/в Docker — локальное обучение даёт лишнюю нагрузку, а сети лёгкие и на CPU
Colab обучаются за секунды. Лёгкие модели (z-score, Isolation Forest) дёшевы и
дообучаются локально через `train_models` — для них Colab не нужен.

Ноутбук **не дублирует** код моделей: он клонирует репу и импортирует те же `ml/`-модули,
что и прод. Артефакт идентичен локальному, т.к. сохранение идёт через тот же
`ModelPersistenceMixin.save`.

## Пайплайн

```
БД → export_training_data (CSV) → Colab (clone + fit + save) → веса → мак → --use-cache
```

### 1. Выгрузить данные с метками в CSV (локально / Render Shell)

```bash
python manage.py export_training_data \
    --device TEMP-001 --metric temperature --output train.csv
```

CSV: `device,metric,value,recorded_at,is_anomaly,anomaly_type`. Метки берутся из
`Telemetry.raw_data['anomaly']` — без них Colab учил бы вслепую и evaluation был бы
невозможен. Формат параллелен `loader.load_series`: `load_series_from_csv` в ноутбуке
собирает байт-в-байт тот же `TimeSeries`, что прод собирает из БД (round-trip покрыт
тестом `test_export_training_data.py`).

### 2. Обучить в Colab

Открыть [`train_colab.ipynb`](train_colab.ipynb) в Colab → выполнить ячейки по порядку:
клонирует репу, ставит пинованные версии, грузит CSV, обучает, сохраняет артефакт,
отдаёт `ml_models.zip` на скачивание.

### 3. Разложить веса локально и проверить

Распаковать `ml_models.zip` в `iot_hub/apps/telemetry/ml/models/`, затем:

```bash
python manage.py detect_anomalies \
    --device TEMP-001 --metric temperature --method autoencoder --use-cache
```

В логе должно появиться `[cache] загружено` — команда взяла веса вместо переобучения.

## Важные нюансы

- **Версии зависимостей.** Ноутбук ставит `torch==2.2.2`, `numpy==1.26.3`,
  `scikit-learn==1.4.2` (из `requirements.txt`). Без пина веса могут чуть отличаться.
- **Учим на CPU.** GPU даёт другой порядок операций → другие веса. Для воспроизводимого
  артефакта обучение идёт на CPU; сети крошечные, CPU Colab их тянет за секунды. GPU —
  осознанное ускорение для будущих больших моделей.
- **Совпадение гиперпараметров.** Ноутбук собирает их через `ml/cli_params.py` — тот же
  источник, что у `train_models`/`detect_anomalies`. Так sha манифеста совпадает и
  `--use-cache` принимает веса без `CacheMismatchError`. Меняете гиперпараметр в ноутбуке —
  зовите `--use-cache` с теми же значениями.
- **ONNX-инференс (инкр.5).** Для `lstm_lf_resid` ноутбук кроме `.pt` пишет рядом `.onnx`
  (`model.export_onnx(stem)` после `save`). Боевой прогноз идёт методом `lstm_lf_resid_onnx`
  через `onnxruntime` — **без torch**, одинаково на любом железе (GPU-веса = CPU-вывод).
  Горизонт (`HORIZON=36`) зашит в граф: экспорт и `forecast_telemetry --horizon` должны
  совпадать. На проде без Colab `.onnx` дописывается командой `export_onnx_models` из `.pt`.
- **Что коммитим.** Ноутбук и README — в репо. Веса (`ml/models/`: `.pt`/`.npz`/`.onnx`/
  `_hw.joblib`) и выгрузки (`*.csv`) — нет (gitignore): данные/бинарь приходят по запросу.

---

# Диагностические тетрадки (Фаза 5)

Эксперименты 01-04 дали честный вывод: **сложные модели проигрывают классике**
(autoencoder < Isolation Forest по F1; LSTM < Holt-Winters по MAE). Фаза 5 углубляет
анализ — отвечает на вопрос **ПОЧЕМУ** и проверяет, можно ли это исправить тюнингом.

| Тетрадка | Диагностирует | Метрики | CSV-данные |
|----------|---------------|---------|------------|
| [`diag_autoencoder.ipynb`](diag_autoencoder.ipynb) | AE-детектор vs IForest | F1/precision/recall/FAR + per-type | `--anomaly-rate 0.02 --seed 7` (с метками) |
| [`diag_lstm.ipynb`](diag_lstm.ipynb) | LSTM-форкастер vs Holt-Winters | MAE/RMSE/sMAPE (rolling-origin) | `--anomaly-rate 0.0 --seed 7` (чистый ряд) |

**Принцип тот же:** тетрадки `git clone` репу и импортируют боевые `ml/`-модули
(`build_detector`/`build_forecaster`, `evaluation`, `forecast_evaluation`, `cli_params`,
`load_series_from_csv`) — метрики НЕ переписываются. Экспериментальные варианты архитектур
живут в ячейках; в `ml/` переносим только доказанного победителя.

**Что приносим обратно из Colab:** `out/diag_ae_results.csv` / `out/diag_lstm_results.csv`
+ PNG-графики + `versions.json` (одним zip). **НЕ сырые веса `.pt`** — анализ ведётся по
таблицам и картинкам, torch для него не нужен.

**Версии НЕ пиним** (в отличие от `train_colab.ipynb` выше): диагностика не возит веса и
учит заново каждый прогон, поэтому воспроизводимость весов не нужна, а пины `numpy 1.x`
под Python 3.12 Colab ломают ABI с предустановленными pandas/matplotlib
(`numpy.dtype size changed`). Детерминизм в рамках прогона даёт `set_torch_determinism(seed)`;
фактические версии Colab пишутся в `versions.json` → в `docs/experiments/05|06_*.md`.

**Структура каждой тетрадки:** setup → данные → baseline-контроль (воспроизводит exp03/04,
sanity-check) → диагностика «почему» (кривые обучения, распределение ошибки по типам / прогноз
vs истина, латентное пространство / автокорреляция) → гипотезы H1-H6 / HL1-HL6 (sweep + кастомные
варианты) → сводка vs baseline → экспорт.

Выводы пишутся в `docs/experiments/05_autoencoder_diagnosis.md` и `06_lstm_diagnosis.md`
в формате exp01-04. Победитель (если найдётся) переносится в `ml/` отдельным шагом.
