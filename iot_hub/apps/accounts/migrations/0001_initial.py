from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserRole',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('admin', 'Администратор'), ('operator', 'Оператор'), ('client', 'Клиент')], default='client', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='role', to='auth.user')),
            ],
            options={
                'verbose_name': 'Роль пользователя',
                'verbose_name_plural': 'Роли пользователей',
                'db_table': 'accounts_userrole',
            },
        ),
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('phone', models.CharField(blank=True, max_length=20, null=True)),
                ('organization', models.CharField(blank=True, max_length=255, null=True)),
                ('avatar', models.ImageField(blank=True, null=True, upload_to='avatars/')),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profile', to='auth.user')),
            ],
            options={
                'verbose_name': 'Профиль пользователя',
                'verbose_name_plural': 'Профили пользователей',
                'db_table': 'accounts_userprofile',
            },
        ),
        migrations.CreateModel(
            name='ApiKey',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=255, unique=True)),
                ('name', models.CharField(max_length=100)),
                ('is_active', models.BooleanField(default=True)),
                ('last_used_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='api_keys', to='auth.user')),
            ],
            options={
                'verbose_name': 'API Ключ',
                'verbose_name_plural': 'API Ключи',
                'db_table': 'accounts_apikey',
            },
        ),
    ]
