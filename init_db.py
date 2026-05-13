#!/usr/bin/env python
"""
Скрипт инициализации БД - создает админа если его нет
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from iot_hub.apps.accounts.models import UserRole, UserProfile

def init_admin():
    """Создает админа если его нет"""
    if User.objects.filter(username='admin').exists():
        print("Admin user already exists")
        return
    
    admin = User.objects.create_superuser(
        username='admin',
        email='admin@mail.ru',
        password='12345'
    )
    
    # Установи роль админа
    admin_role = UserRole.objects.get(user=admin)
    admin_role.role = 'admin'
    admin_role.save()
    
    print(f"Created admin user: admin@mail.ru / 12345 (role: admin)")
    return admin

if __name__ == '__main__':
    init_admin()
