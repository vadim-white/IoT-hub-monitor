from django.urls import path, include
from rest_framework.routers import DefaultRouter
from iot_hub.apps.devices.presentation import views

router = DefaultRouter()
router.register(r'devices', views.DeviceViewSet, basename='device')
router.register(r'types', views.DeviceTypeViewSet, basename='devicetype')
router.register(r'metrics', views.DeviceMetricViewSet, basename='metric')
router.register(r'thresholds', views.AlertThresholdViewSet, basename='threshold')

urlpatterns = [
    path('', include(router.urls)),
]
