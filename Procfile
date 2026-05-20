web: python manage.py migrate && python init_db.py && python load_telemetry_data.py && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
