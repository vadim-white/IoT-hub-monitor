from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from iot_hub.apps.devices.models import Device
from iot_hub.apps.alerts.models import Alert
from iot_hub.apps.telemetry.models import Telemetry


def index(request):
    """Главная страница."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'home.html')


@login_required(login_url='login')
def dashboard(request):
    """Главный дашборд системы."""
    import json
    from django.db.models import Avg
    
    user = request.user
    
    # Определяем доступные устройства - с select_related для оптимизации
    try:
        is_admin = user.role.is_admin if hasattr(user, 'role') else False
    except:
        is_admin = False
    
    if is_admin:
        devices_qs = Device.objects.all()
        alerts_qs = Alert.objects.all()
    else:
        devices_qs = Device.objects.filter(owner=user)
        alerts_qs = Alert.objects.filter(device__owner=user)
    
    # Оптимизировано: все статистики в одном query через annotations
    from django.db.models import Count as CountFunc, Q as QFunc
    
    devices_stats = devices_qs.aggregate(
        total=CountFunc('id'),
        active=CountFunc('id', filter=QFunc(status='active', is_active=True)),
        inactive=CountFunc('id', filter=QFunc(status='inactive')),
        error=CountFunc('id', filter=QFunc(status='error')),
    )
    
    alerts_stats = alerts_qs.aggregate(
        new=CountFunc('id', filter=QFunc(status='new')),
        critical=CountFunc('id', filter=QFunc(severity='critical')),
        acknowledged=CountFunc('id', filter=QFunc(status='acknowledged')),
    )
    
    # Последние алерты - с select_related
    recent_alerts = alerts_qs.select_related('device', 'metric')[:10]
    
    # Последние события телеметрии
    last_24h = timezone.now() - timedelta(hours=24)
    device_ids = list(devices_qs.values_list('id', flat=True)[:100])  # Limit to prevent memory issue
    
    if device_ids:
        recent_telemetry = Telemetry.objects.filter(
            device_id__in=device_ids,
            recorded_at__gte=last_24h
        ).select_related('device', 'metric').order_by('-recorded_at')[:20]
    else:
        recent_telemetry = []
    
    # Активные устройства за последние 5 минут
    five_min_ago = timezone.now() - timedelta(minutes=5)
    active_now_count = devices_qs.filter(last_seen_at__gte=five_min_ago).count()
    
    # Данные для графиков - группируем по типам метрик
    charts_data = []
    
    # Ключевые метрики для визуализации
    metric_groups = [
        {'name': 'Температура', 'metric_type': 'temperature', 'unit': '°C'},
        {'name': 'Влажность', 'metric_type': 'humidity', 'unit': '%'},
        {'name': 'Мощность', 'metric_type': 'power', 'unit': 'Wh'},
    ]
    
    for group in metric_groups:
        # Получаем все устройства с данным типом метрики
        devices_with_metric = Device.objects.filter(
            metrics__metric_type=group['metric_type'],
            metrics__is_active=True
        ).prefetch_related('telemetry')
        
        if is_admin:
            pass  # уже все
        else:
            devices_with_metric = devices_with_metric.filter(owner=user)
        
        chart_devices = []
        
        for device in devices_with_metric[:6]:  # Макс 6 линий на графике
            # Получаем последние 30 дней данных
            telemetry_data = Telemetry.objects.filter(
                device=device,
                metric__metric_type=group['metric_type']
            ).order_by('recorded_at')[:30]
            
            if telemetry_data.exists():
                labels = [t.recorded_at.strftime('%d.%m') for t in telemetry_data]
                values = [t.value for t in telemetry_data]
                
                chart_devices.append({
                    'name': device.name,
                    'labels': labels,
                    'values': values,
                })
        
        if chart_devices:
            charts_data.append({
                'title': group['name'],
                'unit': group['unit'],
                'devices': chart_devices,
            })
    
    context = {
        'total_devices': devices_stats['total'],
        'active_devices': devices_stats['active'],
        'inactive_devices': devices_stats['inactive'],
        'error_devices': devices_stats['error'],
        'new_alerts': alerts_stats['new'],
        'critical_alerts': alerts_stats['critical'],
        'acknowledged_alerts': alerts_stats['acknowledged'],
        'recent_alerts': recent_alerts,
        'recent_telemetry': recent_telemetry,
        'active_now': active_now_count,
        'charts_data': json.dumps(charts_data),
    }
    
    return render(request, 'dashboard/dashboard.html', context)


@login_required(login_url='login')
def devices_list(request):
    """Список устройств."""
    user = request.user
    if hasattr(user, 'role') and user.role.is_admin:
        devices = Device.objects.all()
    else:
        devices = Device.objects.filter(owner=user)
    
    context = {'devices': devices}
    return render(request, 'devices/list.html', context)


@login_required(login_url='login')
def device_detail(request, device_id):
    """Детали устройства."""
    device = Device.objects.get(id=device_id)
    context = {'device': device}
    return render(request, 'devices/detail.html', context)


@login_required(login_url='login')
def alerts_list(request):
    """Список алертов."""
    user = request.user
    if hasattr(user, 'role') and user.role.is_admin:
        alerts = Alert.objects.all()
    else:
        alerts = Alert.objects.filter(device__owner=user)
    
    context = {'alerts': alerts}
    return render(request, 'alerts/list.html', context)


@login_required(login_url='login')
def telemetry_view(request):
    """Просмотр телеметрии."""
    user = request.user
    if hasattr(user, 'role') and user.role.is_admin:
        telemetry = Telemetry.objects.all()
    else:
        telemetry = Telemetry.objects.filter(device__owner=user)
    
    context = {'telemetry': telemetry}
    return render(request, 'telemetry/list.html', context)
