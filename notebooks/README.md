# Обучение ML-моделей в Google Colab (Фаза 4, инкремент 2)

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
- **Что коммитим.** Ноутбук и README — в репо. Веса (`ml/models/`) и выгрузки
  (`*.csv`) — нет (gitignore): данные/бинарь приходят по запросу, не версионируются.
