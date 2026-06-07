"""Утилиты и вспомогательные функции."""
import csv
import json
from django.http import HttpResponse
from django.utils import timezone


def export_telemetry_csv(telemetry_qs, filename='telemetry.csv'):
    """Экспорт телеметрии в CSV."""
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    telemetry_qs = telemetry_qs.select_related('device__device_type', 'metric')

    # utf-8-sig добавляет BOM — Excel на Mac/Windows автоматически определяет UTF-8
    writer = csv.writer(response)
    writer.writerow([
        'Device Name', 'Serial Number', 'Device Type',
        'Metric Name', 'Metric Type', 'Value', 'Unit', 'Status', 'Recorded At',
    ])

    for t in telemetry_qs:
        writer.writerow([
            t.device.name,
            t.device.serial_number,
            t.device.device_type.name if t.device.device_type else '',
            t.metric.name,
            t.metric.metric_type,
            t.value,
            t.unit,
            t.status,
            t.recorded_at.strftime('%Y-%m-%d %H:%M:%S'),
        ])

    return response


def export_telemetry_json(telemetry_qs, filename='telemetry.json', meta=None):
    """Экспорт телеметрии в JSON — данные сгруппированы по устройствам."""
    response = HttpResponse(content_type='application/json; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    telemetry_qs = telemetry_qs.select_related('device__device_type', 'metric')
    records = list(telemetry_qs)

    # Группируем: ключ = device_id, устройство и его readings — плоско внутри
    devices_map = {}
    for t in records:
        did = str(t.device.id)
        if did not in devices_map:
            devices_map[did] = {
                'id': did,
                'name': t.device.name,
                'serial_number': t.device.serial_number,
                'type': t.device.device_type.name if t.device.device_type else None,
                'readings': [],
            }
        devices_map[did]['readings'].append({
            'metric_name': t.metric.name,
            'metric_type': t.metric.metric_type,
            'value': t.value,
            'unit': t.unit,
            'status': t.status,
            'recorded_at': t.recorded_at.isoformat(),
        })

    export_meta = meta or {}
    export_meta.setdefault('generated_at', timezone.now().isoformat())
    export_meta.setdefault('record_count', len(records))
    export_meta.setdefault('device_count', len(devices_map))

    payload = {'export_meta': export_meta, 'data': devices_map}
    response.write(json.dumps(payload, indent=2, ensure_ascii=False))
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
