from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserRole(models.Model):
    """Модель ролей пользователя."""
    ROLE_CHOICES = (
        ('admin', 'Администратор'),
        ('operator', 'Оператор'),
        ('client', 'Клиент'),
    )
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='role')
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='client'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Роль пользователя'
        verbose_name_plural = 'Роли пользователей'
        db_table = 'accounts_userrole'
        
    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"
    
    @property
    def is_admin(self):
        return self.role == 'admin'
    
    @property
    def is_operator(self):
        return self.role == 'operator'
    
    @property
    def is_client(self):
        return self.role == 'client'


class UserProfile(models.Model):
    """Расширенный профиль пользователя."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone = models.CharField(max_length=20, blank=True, null=True)
    organization = models.CharField(max_length=255, blank=True, null=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Профиль пользователя'
        verbose_name_plural = 'Профили пользователей'
        db_table = 'accounts_userprofile'
        
    def __str__(self):
        return f"Profile of {self.user.username}"


class ApiKey(models.Model):
    """API ключи для программного доступа."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_keys')
    key = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'API Ключ'
        verbose_name_plural = 'API Ключи'
        db_table = 'accounts_apikey'
    
    def __str__(self):
        return f"{self.name} ({self.user.username})"


# Signals
@receiver(post_save, sender=User)
def create_user_role(sender, instance, created, **kwargs):
    """Автоматически создаёт роль при создании пользователя."""
    if created:
        UserRole.objects.get_or_create(user=instance, defaults={'role': 'client'})


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Автоматически создаёт профиль при создании пользователя."""
    if created:
        UserProfile.objects.get_or_create(user=instance)
