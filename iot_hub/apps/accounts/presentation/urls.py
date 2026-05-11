from django.urls import path, include
from rest_framework.routers import DefaultRouter
from iot_hub.apps.accounts.presentation import views

router = DefaultRouter()
router.register(r'users', views.UserViewSet, basename='user')
router.register(r'roles', views.UserRoleViewSet, basename='role')
router.register(r'keys', views.ApiKeyViewSet, basename='apikey')

urlpatterns = [
    path('', include(router.urls)),
]
