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
    
    # Check if we should initialize data (only if database is fresh)
    import django
    django.setup()
    from django.db import connection
    
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

    # Seed demo alerts
    run_command(
        "python seed_alerts.py",
        "Seeding demo alerts"
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
