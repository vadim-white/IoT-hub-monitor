FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app:/app/iot_hub
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DJANGO_SETTINGS_MODULE=iot_hub.config.settings

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy project
COPY . .

# Create necessary directories
RUN mkdir -p logs staticfiles media

EXPOSE 8080

CMD ["sh", "-c", "mkdir -p /app/logs && python manage.py makemigrations --noinput 2>&1 || true && python manage.py migrate --noinput && python init_db.py && python load_telemetry_data.py && gunicorn iot_hub.config.wsgi:application --bind 0.0.0.0:8080 --workers 4 --worker-class sync --timeout 300 --keep-alive 5 --max-requests 1000 --max-requests-jitter 50 --access-logfile - --error-logfile - --log-level info"]