from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='DeviceType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('description', models.TextField(blank=True)),
                ('manufacturer', models.CharField(blank=True, max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Тип устройства',
                'verbose_name_plural': 'Типы устройств',
                'db_table': 'devices_devicetype',
            },
        ),
        migrations.CreateModel(
            name='Device',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('serial_number', models.CharField(max_length=50, unique=True)),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('active', 'Активно'), ('inactive', 'Неактивно'), ('disconnected', 'Отключено'), ('error', 'Ошибка')], default='inactive', max_length=20)),
                ('latitude', models.FloatField(blank=True, null=True)),
                ('longitude', models.FloatField(blank=True, null=True)),
                ('location_name', models.CharField(blank=True, max_length=255)),
                ('is_active', models.BooleanField(default=True)),
                ('installation_date', models.DateTimeField(blank=True, null=True)),
                ('last_seen_at', models.DateTimeField(blank=True, null=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('device_type', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='devices.devicetype')),
                ('owner', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='owned_devices', to='auth.user')),
            ],
            options={
                'verbose_name': 'IoT-устройство',
                'verbose_name_plural': 'IoT-устройства',
                'db_table': 'devices_device',
            },
        ),
        migrations.CreateModel(
            name='DeviceMetric',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('metric_type', models.CharField(choices=[('temperature', 'Температура (°C)'), ('humidity', 'Влажность (%)'), ('voltage', 'Напряжение (V)'), ('current', 'Ток (A)'), ('power', 'Мощность (W)'), ('rssi', 'Сила сигнала (dBm)'), ('uptime', 'Время работы (s)'), ('error_count', 'Количество ошибок'), ('custom', 'Пользовательский')], max_length=50)),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('unit', models.CharField(blank=True, max_length=50)),
                ('min_value', models.FloatField(blank=True, null=True)),
                ('max_value', models.FloatField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='metrics', to='devices.device')),
            ],
            options={
                'verbose_name': 'Метрика устройства',
                'verbose_name_plural': 'Метрики устройств',
                'db_table': 'devices_devicemetric',
            },
        ),
        migrations.CreateModel(
            name='AlertThreshold',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('severity', models.CharField(choices=[('info', 'Информация'), ('warning', 'Предупреждение'), ('critical', 'Критичный')], default='warning', max_length=20)),
                ('lower_bound', models.FloatField(blank=True, null=True)),
                ('upper_bound', models.FloatField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('metric', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='thresholds', to='devices.devicemetric')),
            ],
            options={
                'verbose_name': 'Порог алерта',
                'verbose_name_plural': 'Пороги алертов',
                'db_table': 'devices_alertthreshold',
            },
        ),
        migrations.AddIndex(
            model_name='device',
            index=models.Index(fields=['owner', 'status'], name='devices_dev_owner_id_status_idx'),
        ),
        migrations.AddIndex(
            model_name='device',
            index=models.Index(fields=['last_seen_at'], name='devices_dev_last_se_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='devicemetric',
            unique_together={('device', 'metric_type')},
        ),
    ]
