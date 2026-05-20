#!/bin/bash
set -e

echo "Running migrations..."
python manage.py migrate

echo "Initializing database..."
python init_db.py

echo "Loading telemetry data..."
python load_telemetry_data.py

echo "Starting gunicorn..."
exec gunicorn iot_hub.config.wsgi:application --bind 0.0.0.0:$PORT --workers 4
