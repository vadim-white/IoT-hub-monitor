"""Создание алертов из ML-результатов (аномалии и предиктивные прогнозы).

Единая точка записи ML-находок в модель Alert — переиспользуется командами
detect_anomalies и forecast_telemetry. Дедупликация по окну времени защищает от
дублей при повторных прогонах команды (см. docs/plans/ML_CORE_alerts_ui.md).
"""
from datetime import timedelta

from django.utils import timezone

from iot_hub.apps.alerts.models import Alert, AlertHistory

OPEN_STATUSES = ('new', 'acknowledged')


def create_ml_alert(*, device, metric, source, severity, value, message,
                    telemetry=None, metadata=None, dedup_hours=6):
    """Создаёт ML-алерт или возвращает существующий открытый дубль.

    Дедуп: если по этому device+metric уже есть открытый (new/acknowledged) алерт
    того же source за последние dedup_hours — новый не создаётся, возвращается он.

    Возвращает (alert, created): created=False, если вернули существующий дубль.
    """
    if dedup_hours:
        cutoff = timezone.now() - timedelta(hours=dedup_hours)
        existing = Alert.objects.filter(
            device=device, metric=metric, source=source,
            status__in=OPEN_STATUSES, created_at__gte=cutoff,
        ).first()
        if existing is not None:
            return existing, False

    alert = Alert.objects.create(
        device=device, metric=metric, source=source, severity=severity,
        value=value, message=message, telemetry=telemetry,
        metadata=metadata or {}, status='new', threshold=None,
    )
    AlertHistory.objects.create(
        alert=alert, action='created',
        comment=f'Создан автоматически ({alert.get_source_display()})',
    )
    return alert, True
