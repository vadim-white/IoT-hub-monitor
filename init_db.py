#!/usr/bin/env python
"""
Скрипт инициализации БД - проверяет админа и его роль.
Основное создание админа происходит в миграции accounts/0002_create_admin_user.py
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iot_hub.config.settings')
django.setup()

from django.contrib.auth.models import User
from iot_hub.apps.accounts.models import UserRole


def ensure_admin():
    """Проверяет/создает админа и его роль если их нет."""
    admin = User.objects.filter(username='admin').first()
    
    if not admin:
        # На случай если миграция не отработала
        admin = User.objects.create_superuser(
            username='admin',
            email='admin@mail.ru',
            password='12345'
        )
        print("⚠️  Администратор создан скриптом (миграция могла не отработать)")
    
    # Проверяем роль
    try:
        role = admin.role
        print(f"✅ Администратор: {admin.username} (роль: {role.role})")
    except UserRole.DoesNotExist:
        # На случай если роль не создалась в миграции
        UserRole.objects.create(user=admin, role='admin')
        print(f"✅ Администратор: {admin.username} (роль создана)")
    
    return admin


if __name__ == '__main__':
    ensure_admin()
