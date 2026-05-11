from django.urls import path, include
from rest_framework.routers import DefaultRouter
from iot_hub.apps.telemetry.presentation import views

router = DefaultRouter()
router.register(r'readings', views.TelemetryViewSet, basename='telemetry')
router.register(r'statistics', views.TelemetryStatisticsViewSet, basename='statistics')

urlpatterns = [
    path('', include(router.urls)),
]
