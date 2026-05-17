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

CMD ["gunicorn", "iot_hub.config.wsgi:application", "--bind", "0.0.0.0:8080", "--workers", "4"]