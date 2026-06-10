# IoT Hub Monitor

Система мониторинга IoT-устройств в реальном времени с веб-интерфейсом, аналитикой и управлением алертами.

## 🌐 Демо

**[https://iot-hub-monitor-ucs6.onrender.com](https://iot-hub-monitor-ucs6.onrender.com)**

> Первый запрос после простоя может занять ~30 сек (free tier засыпает).

---

## 🚀 Возможности

- 📊 **Мониторинг в реальном времени** — отслеживание метрик устройств с мгновенными обновлениями
- 🔔 **Умные алерты** — уведомления о критических событиях и аномалиях
- 🎛️ **Ручная настройка алертов** — создание и редактирование порогов срабатывания (нижняя/верхняя граница, уровень severity) прямо из карточки устройства
- 📈 **Аналитика и графики** — визуализация данных через Chart.js (30-дневный период)
- 🧩 **Управление устройствами** — добавление, настройка и контроль состояния IoT-устройств
- 📥 **Экспорт телеметрии** — выгрузка данных в CSV и JSON с выбором устройств и периода
- 🔐 **Безопасность** — аутентификация пользователей и ролевая модель доступа
- ♻️ **Масштабируемость** — архитектура, готовая к росту количества устройств

---

## 🛠 Технологии

| Компонент | Технология |
|-----------|-----------|
| **Backend** | Python 3.11+, Django, Django REST Framework |
| **Database** | PostgreSQL |
| **Frontend** | HTML5, CSS3, JavaScript, Chart.js |
| **Контейнеризация** | Docker, Docker Compose |
| **Аутентификация** | Django Auth, Token Authentication |
| **Безопасность** | Custom Security Middleware (SQL injection, XSS, path traversal) |

---

## 📦 Структура проекта

```
IoT-hub-monitor/
├── docker-compose.yml      # Конфигурация сервисов
├── Dockerfile              # Образ приложения
├── requirements.txt        # Зависимости Python
├── manage.py               # Точка входа Django
├── run_fuzzing_tests.py    # Fuzzing тесты безопасности
├── datasets/               # Реальные датасеты для калибровки (gitignore, кроме energydata)
├── tools/                  # Утилиты: extract_profiles.py (профили метрик из датасетов)
├── docs/                   # Внутренняя документация (gitignore)
├── iot_hub/
│   ├── apps/
│   │   ├── accounts/       # Аутентификация и профили пользователей
│   │   ├── devices/        # Модели и логика IoT-устройств
│   │   ├── alerts/         # Система уведомлений и алертов
│   │   ├── telemetry/      # Сбор и обработка телеметрии
│   │   ├── audit/          # Логирование действий
│   │   ├── dashboard/      # Визуализация данных
│   │   └── common/         # Общие утилиты и middleware
│   ├── config/             # Конфигурация Django
│   ├── static/             # CSS, JS, изображения
│   └── templates/          # HTML-шаблоны
├── tests/                  # Дополнительные тесты
└── README.md               # Этот файл
```

---

## ⚙️ Запуск проекта

### Требования
- Docker и Docker Compose
- Минимум 2 ГБ ОЗУ для контейнеров

### Пошаговая инструкция

1. **Клонирование репозитория**
   ```bash
   git clone <ваш-репозиторий>
   cd IoT-hub-monitor
   ```

2. **Сборка и запуск контейнеров**
   ```bash
   # Сборка образов (если есть изменения в Dockerfile)
   docker-compose build

   # Запуск в фоновом режиме с пересозданием контейнеров
   docker-compose up -d --force-recreate
   ```

3. **Проверка статуса**
   ```bash
   docker-compose ps
   # Ожидаемый результат: все контейнеры в статусе "Up"
   ```

4. **Доступ к приложению**
   - Веб-интерфейс: [http://127.0.0.1:8080](http://127.0.0.1:8080)
   - Django Admin: [http://127.0.0.1:8080/admin](http://127.0.0.1:8080/admin) (логин: `admin`, пароль: `12345`)

   При первом запуске автоматически создаются тестовые пользователи:

   | Логин | Пароль | Роль | Устройств |
   |-------|--------|------|-----------|
   | `admin` | `12345` | Администратор | 10 |
   | `operator1` | `operator123` | Оператор | 5 |
   | `operator2` | `operator123` | Оператор | 5 |
   | `client1` | `client123` | Клиент | 5 |


---

## 📥 Экспорт телеметрии

Страница `/export/` — выгрузка телеметрии выбранных устройств за произвольный период.

| Формат | Поля |
|--------|------|
| **CSV** | Device Name, Serial Number, Device Type, Metric Name, Metric Type, Value, Unit, Status, Recorded At |
| **JSON** | Сгруппировано по `device_id`: метаданные экспорта + объект устройства со списком `readings` |

> CSV сохраняется в UTF-8 с BOM — корректно открывается в Excel на Mac и Windows.

---

## 📚 Датасеты

Для калибровки генератора синтетической телеметрии и ML-экспериментов (обнаружение
аномалий, предиктивные алерты) используются реальные открытые датасеты. Они лежат
в папке `datasets/` (в `.gitignore`, кроме `energydata_complete.csv` — он нужен для
демо-данных при первом запуске). Из них извлекаются статистические профили метрик
(`tools/extract_profiles.py` → `iot_hub/apps/telemetry/profiles/*.json`).

| Датасет | Назначение | Метрики | Источник |
|---------|------------|---------|----------|
| **energydata_complete** (UCI Appliances Energy) | Демо-телеметрия + профили комнатных датчиков | temperature, humidity, power | [UCI #374](https://archive.ics.uci.edu/dataset/374/) |
| **Погода РФ** (Москва: Балчуг, ВДНХ, 2025) | Профиль уличного датчика, климат РФ | temperature, humidity | [rp5.ru](https://rp5.ru) — «Расписание Погоды» |
| **Household Power Consumption** | Профили электрики | voltage, current, power | [UCI #235](https://archive.ics.uci.edu/dataset/235/) |
| **AI4I 2020 Predictive Maintenance** | Метки отказов для гибридного rule+ML алертинга | температура, момент, износ | [UCI #601](https://archive.ics.uci.edu/dataset/601/) |
| **NASA C-MAPSS** | Деградация до отказа (RUL) для предиктивных алертов | сенсоры турбин | [NASA PCoE](https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/) |
| **Numenta NAB** | Бенчмарк аномалий (размеченные окна) для сравнения ML-методов | time-series | [github.com/numenta/NAB](https://github.com/numenta/NAB) |

> Данные погоды предоставлены сайтом **«Расписание Погоды», [rp5.ru](https://rp5.ru)** —
> при использовании этих данных просьба указывать названный сайт.

Подробный анализ датасетов и дизайн симулятора — во внутренней документации (`docs/simulator/`).

---

## 🛑 Остановка и очистка

```bash
# Остановка контейнеров с удалением томов (полный сброс БД и данных)
docker-compose down -v

# Только остановка (данные сохранятся)
docker-compose down
```

> ⚠️ Флаг `-v` удаляет volumes: `postgres_data`, `static_volume`, `media_volume`. Используйте только при необходимости полного сброса.

---

## 🔧 Полезные команды

| Команда | Описание |
|---------|----------|
| `docker-compose logs -f web` | Просмотр логов Django-приложения |
| `docker-compose exec web python manage.py shell` | Открыть Django shell в контейнере |
| `docker-compose exec db psql -U user iot_hub` | Подключиться к PostgreSQL |
| `docker-compose build --no-cache` | Пересобрать образы без кэша |

---

## 🗄️ База данных

- **Тип**: PostgreSQL
- **Порт**: 5432 (внутри сети Docker)
- **Миграции** применяются автоматически при старте контейнера `web`

Для создания суперпользователя:
```bash
docker-compose exec web python manage.py createsuperuser
```

---

## 🧪 Разработка

1. Внесите изменения в код
2. Пересоберите образ:
   ```bash
   docker-compose build web
   ```
3. Перезапустите сервис:
   ```bash
   docker-compose up -d --force-recreate web
   ```

---

## Безопасность и тестирование

### Fuzzing тесты
Проект включает comprehensive fuzzing тест-сьют для проверки безопасности API:

```bash
# Запуск fuzzing тестов
docker-compose exec -T web python run_fuzzing_tests.py
```

**Защита от**:
- SQL Injection
- Cross-Site Scripting (XSS)
- Path Traversal
- Command Injection
- Null Byte Injection
- Malformed requests
- RBAC нарушений — разграничение доступа между ролями (admin / operator / client)

Тесты запускаются автоматически в CI/CD pipeline.

---

## 📄 Лицензия

Проект распространяется под лицензией MIT. Подробности — в файле `LICENSE`. 

---



