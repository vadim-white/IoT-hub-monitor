"""
Main URL Configuration for IoT Hub Monitor.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

# Use Django's lazy URL resolution through get_asgi_application
# This function is called after Django is fully initialized by gunicorn/Django
def get_urlpatterns():
    from iot_hub.apps.accounts.presentation import views as account_views
    from iot_hub.apps.dashboard.presentation import views as dashboard_views
    
    patterns = [
        path('admin/', admin.site.urls),
        path('api/auth/', include('iot_hub.apps.accounts.presentation.urls')),
        path('api/devices/', include('iot_hub.apps.devices.presentation.urls')),
        path('api/telemetry/', include('iot_hub.apps.telemetry.presentation.urls')),
        path('api/alerts/', include('iot_hub.apps.alerts.presentation.urls')),
        path('api/audit/', include('iot_hub.apps.audit.presentation.urls')),
        path('api/dashboard/', include('iot_hub.apps.dashboard.presentation.urls')),
        
        # Web pages
        path('', dashboard_views.index, name='index'),
        path('auth/login/', account_views.login_view, name='login'),
        path('auth/register/', account_views.register_view, name='register'),
        path('auth/logout/', account_views.logout_view, name='logout'),
        path('dashboard/', dashboard_views.dashboard, name='dashboard'),
        path('devices/', dashboard_views.devices_list, name='devices_list'),
        path('devices/<uuid:device_id>/', dashboard_views.device_detail, name='device_detail'),
        path('alerts/', dashboard_views.alerts_list, name='alerts_list'),
        path('telemetry/', dashboard_views.telemetry_view, name='telemetry'),
        path('profile/', account_views.profile_view, name='profile'),
    ]
    
    if settings.DEBUG:
        patterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
        patterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    
    return patterns

# Create a lazy wrapper that implements the sequence protocol
class _URLPatternsProxy:
    def __init__(self):
        self._patterns = None
    
    def _ensure_loaded(self):
        if self._patterns is None:
            self._patterns = get_urlpatterns()
    
    def __iter__(self):
        self._ensure_loaded()
        return iter(self._patterns)
    
    def __getitem__(self, idx):
        self._ensure_loaded()
        return self._patterns[idx]
    
    def __len__(self):
        self._ensure_loaded()
        return len(self._patterns)
    
    def __repr__(self):
        self._ensure_loaded()
        return repr(self._patterns)
    
    def __bool__(self):
        self._ensure_loaded()
        return bool(self._patterns)

urlpatterns = _URLPatternsProxy()
