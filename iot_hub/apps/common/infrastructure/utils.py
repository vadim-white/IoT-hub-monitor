"""Утилиты и вспомогательные функции."""
import csv
import json
from datetime import datetime
from django.http import HttpResponse
from iot_hub.apps.telemetry.models import Telemetry


def export_telemetry_csv(telemetry_qs, filename='telemetry.csv'):
    """Экспорт телеметрии в CSV."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    writer.writerow(['Device', 'Metric', 'Value', 'Unit', 'Status', 'Recorded At'])
    
    for t in telemetry_qs:
        writer.writerow([
            t.device.name,
            t.metric.name,
            t.value,
            t.unit,
            t.status,
            t.recorded_at.strftime('%Y-%m-%d %H:%M:%S')
        ])
    
    return response


def export_telemetry_json(telemetry_qs, filename='telemetry.json'):
    """Экспорт телеметрии в JSON."""
    response = HttpResponse(content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    data = []
    for t in telemetry_qs:
        data.append({
            'device': t.device.name,
            'metric': t.metric.name,
            'value': t.value,
            'unit': t.unit,
            'status': t.status,
            'recorded_at': t.recorded_at.isoformat(),
        })
    
    response.write(json.dumps(data, indent=2))
    return response


def calculate_telemetry_stats(telemetry_qs):
    """Вычисление статистики по телеметрии."""
    values = list(telemetry_qs.values_list('value', flat=True))
    
    if not values:
        return None
    
    return {
        'count': len(values),
        'min': min(values),
        'max': max(values),
        'avg': sum(values) / len(values),
    }
