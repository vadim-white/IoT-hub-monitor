from django.contrib import admin
from .models import UserRole, UserProfile, ApiKey


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'created_at')
    list_filter = ('role',)
    search_fields = ('user__username',)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'organization', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('user__username', 'organization')


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ('user', 'name', 'is_active', 'created_at', 'last_used_at')
    list_filter = ('is_active',)
    search_fields = ('user__username', 'name')
