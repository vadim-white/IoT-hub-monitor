#!/usr/bin/env python
"""
Entrypoint script that handles database connection waiting and initialization.
"""
import os
import sys
import time
import subprocess
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add app to path
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/iot_hub')

def wait_for_db(max_retries=30, retry_delay=2):
    """Wait for database to become available."""
    import django
    from django.conf import settings
    from django.db import connection
    
    logger.info("Waiting for database to become available...")
    
    for attempt in range(max_retries):
        try:
            # Configure Django if not already configured
            if not settings.configured:
                os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iot_hub.config.settings')
                django.setup()
            
            # Try to connect
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
            logger.info("✓ Database connection successful!")
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Database not ready (attempt {attempt + 1}/{max_retries}): {str(e)[:100]}")
                time.sleep(retry_delay)
            else:
                logger.error(f"Failed to connect to database after {max_retries} attempts")
                return False
    
    return False


def run_command(cmd, description="Running command"):
    """Run a command and return success status."""
    logger.info(f"{description}...")
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd='/app',
            capture_output=False,
            text=True
        )
        if result.returncode != 0:
            logger.warning(f"Command returned non-zero exit code: {result.returncode}")
            return False
        return True
    except Exception as e:
        logger.error(f"Error running command: {e}")
        return False


def main():
    """Main entrypoint function."""
    # Create necessary directories
    logger.info("Creating necessary directories...")
    Path('/app/logs').mkdir(parents=True, exist_ok=True)
    Path('/app/staticfiles').mkdir(parents=True, exist_ok=True)
    Path('/app/media').mkdir(parents=True, exist_ok=True)
    
    # Wait for database
    if not wait_for_db():
        logger.error("Database is not available. Exiting.")
        sys.exit(1)
    
    # Run Django setup
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iot_hub.config.settings')
    
    # Run migrations
    run_command(
        "python manage.py makemigrations --noinput",
        "Running makemigrations"
    )
    run_command(
        "python manage.py migrate --noinput",
        "Running migrate"
    )

    # Collect static files
    run_command(
        "python manage.py collectstatic --noinput",
        "Collecting static files"
    )
    
    import django
    django.setup()
    from django.db import connection

    # Демо-данные (init_db / load / shift / seed / last_seen) разрушительны: они
    # сбрасывают телеметрию и пересоздают алерты. Нужны для свежего демо НА RENDER,
    # но мешают локальной разработке (стирают наши ML-алерты при каждом рестарте).
    # Render всегда выставляет RENDER_EXTERNAL_HOSTNAME — по нему и отличаем прод.
    # Локально шаг пропускается (FORCE_SEED_DEMO=1 — принудительно прогнать вручную).
    on_render = bool(os.environ.get('RENDER_EXTERNAL_HOSTNAME'))
    seed_demo = on_render or os.environ.get('FORCE_SEED_DEMO') == '1'

    if not seed_demo:
        logger.info("Локальный запуск (нет RENDER_EXTERNAL_HOSTNAME) — "
                    "демо-данные НЕ пересоздаются, существующие данные сохранены. "
                    "Для принудительного сидинга: FORCE_SEED_DEMO=1.")
    else:
        # Check if we should initialize data (only if database is fresh)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'")
                table_count = cursor.fetchone()[0]

            # If we have schema tables, init_db.py already ran
            if table_count > 0:
                logger.info("Database already initialized, skipping init_db.py")
            else:
                run_command("python init_db.py", "Initializing database")
        except Exception as e:
            logger.warning(f"Could not check table count: {e}")

        # Load telemetry data
        run_command(
            "python load_telemetry_data.py",
            "Loading telemetry data"
        )

        # Shift telemetry dates so the latest record is always today
        run_command(
            "python shift_telemetry_dates.py",
            "Shifting telemetry dates to today"
        )

        # Seed demo alerts (always reset to keep data fresh)
        run_command(
            "python seed_alerts.py --reset",
            "Seeding demo alerts"
        )

        # Refresh last_seen_at for ALL devices on every deploy so time stays fresh
        try:
            import random
            from django.utils import timezone
            from datetime import timedelta
            from iot_hub.apps.devices.models import Device
            devices = list(Device.objects.all())
            for device in devices:
                device.last_seen_at = timezone.now() - timedelta(minutes=random.randint(1, 60))
            if devices:
                Device.objects.bulk_update(devices, ['last_seen_at'])
                logger.info(f"✅ Обновлено last_seen_at для {len(devices)} устройств")
            else:
                logger.info("✅ Нет устройств для обновления last_seen_at")
        except Exception as e:
            logger.warning(f"Could not refresh last_seen_at: {e}")

        # ── Реальный ML-инференс (Фаза 4 инкр.3) ──────────────────────────────
        # Раньше ML-секцию на Render показывала статичная заглушка ML_DEMO в
        # seed_alerts.py. Теперь считаем НАСТОЯЩИЕ ML-алерты по живой телеметрии,
        # по ОДНОМУ temperature-устройству на каждого из 4 демо-юзеров (RBAC: юзер
        # видит только свои алерты → витрина ML нужна у каждого, не только у admin).
        # На каждое устройство:
        # 1) гарантируем порог AlertThreshold upper=51.8 (seed создаёт пороги
        #    СЛУЧАЙНО — на конкретном устройстве его может не быть, тогда forecast
        #    не сработает; get_or_create делает forecast-алерт детерминированным);
        # 2) генерируем наблюдаемые аномалии + деградацию (реальный датасет «чистый»);
        # 3) IsolationForest (w72/c0.01 — лучший режим из эксп.02) → ml_anomaly;
        # 4) Holt-Winters → ml_forecast (прогноз пересекает порог 51.8°C).
        # Лёгкие модели обучаются здесь же из managed Postgres (секунды), веса не
        # возим (ml/models/ в .gitignore). Каждый шаг best-effort: сбой не валит деплой.
        # ВАЖНО: только под seed_demo (Render/FORCE_SEED_DEMO) — локально пропуск.
        # См. docs/plans/phase4/03_render_inference.md.
        # degradation-rate 2.9 / start-frac 0.7 / seed 7: хвост подбирается к порогу
        # 51.8°C (50+1.8 из шаблона seed_alerts), прогноз Holt-Winters его пересекает.
        # rate 2.9 (не 2.65) — чтобы ВСЕ 4 устройства с разными energydata-профилями
        # гарантированно пересекали порог. window 72 + contamination 0.01 — лучший
        # режим IF из docs/experiments/02 (precision ~1.0, FAR ~0). --tail 2000: зона
        # деградации (хвост ~30%) глушит точечные выбросы, и у разных профилей они на
        # разной глубине (до ~1700 точек) → tail 2000 (~2 нед) ловит аномалию у всех.
        ml_devices = ["TEMP-001", "TEMP-004", "TEMP-006", "TEMP-008"]

        # (1) гарантируем порог 51.8°C на temperature каждого ML-устройства —
        # иначе forecast-алерт зависит от случайной выборки seed_alerts.
        ensure_thresholds = (
            "python manage.py shell -c "
            "\"from iot_hub.apps.devices.models import Device, AlertThreshold; "
            "[AlertThreshold.objects.get_or_create("
            "metric=Device.objects.get(serial_number=sn).metrics.get(metric_type='temperature'), "
            "severity='info', upper_bound=51.8, defaults={'is_active': True}) "
            "for sn in ['TEMP-001','TEMP-004','TEMP-006','TEMP-008']]\""
        )
        run_command(ensure_thresholds, "ML: гарантия порога 51.8°C на ML-устройствах")

        # (2-4) генерация → детекция → прогноз по каждому устройству
        for sn in ml_devices:
            run_command(
                f"python manage.py generate_telemetry --devices {sn} "
                "--anomaly-rate 0.05 --degradation --degradation-rate 2.9 "
                "--degradation-start-frac 0.7 --seed 7",
                f"ML[{sn}]: генерация аномалий+деградации",
            )
            run_command(
                f"python manage.py detect_anomalies --device {sn} "
                "--metric temperature --method iforest --window 72 "
                "--contamination 0.01 --threshold 0.0 --tail 2000 --write-alerts",
                f"ML[{sn}]: детекция (IsolationForest) → ml_anomaly",
            )
            run_command(
                f"python manage.py forecast_telemetry --device {sn} "
                "--metric temperature --method holtwinters --write-alerts",
                f"ML[{sn}]: прогноз (Holt-Winters) → ml_forecast",
            )

    # Start gunicorn
    logger.info("Starting gunicorn...")
    cmd = (
        "gunicorn iot_hub.config.wsgi:application "
        "--bind 0.0.0.0:8080 "
        "--workers 4 "
        "--worker-class sync "
        "--timeout 300 "
        "--keep-alive 5 "
        "--max-requests 1000 "
        "--max-requests-jitter 50 "
        "--access-logfile - "
        "--error-logfile - "
        "--log-level info"
    )
    os.execvp('sh', ['sh', '-c', cmd])


if __name__ == '__main__':
    main()
