from django.urls import path, include
from rest_framework.routers import DefaultRouter
from iot_hub.apps.audit.presentation import views

router = DefaultRouter()
router.register(r'logs', views.AuditLogViewSet, basename='auditlog')

urlpatterns = [
    path('', include(router.urls)),
]
