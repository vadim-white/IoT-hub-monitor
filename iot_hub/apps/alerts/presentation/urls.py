from django.urls import path, include
from rest_framework.routers import DefaultRouter
from iot_hub.apps.alerts.presentation import views

router = DefaultRouter()
router.register(r'alerts', views.AlertViewSet, basename='alert')
router.register(r'notifications', views.AlertNotificationViewSet, basename='notification')

urlpatterns = [
    path('', include(router.urls)),
]
