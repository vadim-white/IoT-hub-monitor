from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('telemetry', '0001_initial'),
        ('devices', '0001_initial'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='Alert',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('severity', models.CharField(choices=[('info', 'Информация'), ('warning', 'Предупреждение'), ('critical', 'Критичный')], default='warning', max_length=20)),
                ('status', models.CharField(choices=[('new', 'Новый'), ('acknowledged', 'Подтвержден'), ('resolved', 'Разрешен'), ('closed', 'Закрыт')], default='new', max_length=20)),
                ('message', models.TextField()),
                ('value', models.FloatField()),
                ('acknowledged_at', models.DateTimeField(blank=True, null=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('acknowledged_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='acknowledged_alerts', to='auth.user')),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='alerts', to='devices.device')),
                ('metric', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='alerts', to='devices.devicemetric')),
                ('resolved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='resolved_alerts', to='auth.user')),
                ('telemetry', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='alert', to='telemetry.telemetry')),
                ('threshold', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='alerts', to='devices.alertthreshold')),
            ],
            options={
                'verbose_name': 'Алерт',
                'verbose_name_plural': 'Алерты',
                'db_table': 'alerts_alert',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='AlertHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('created', 'Создан'), ('acknowledged', 'Подтвержден'), ('resolved', 'Разрешен'), ('closed', 'Закрыт'), ('reopened', 'Переоткрыт')], max_length=20)),
                ('comment', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.user')),
                ('alert', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='history', to='alerts.alert')),
            ],
            options={
                'verbose_name': 'История алерта',
                'verbose_name_plural': 'Истории алертов',
                'db_table': 'alerts_history',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='AlertNotification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('notification_type', models.CharField(choices=[('email', 'Email'), ('sms', 'SMS'), ('push', 'Push'), ('in_app', 'In-App')], max_length=20)),
                ('sent_at', models.DateTimeField(auto_now_add=True)),
                ('read_at', models.DateTimeField(blank=True, null=True)),
                ('content', models.TextField()),
                ('external_id', models.CharField(blank=True, max_length=255)),
                ('alert', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='alerts.alert')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='alert_notifications', to='auth.user')),
            ],
            options={
                'verbose_name': 'Уведомление об алерте',
                'verbose_name_plural': 'Уведомления об алертах',
                'db_table': 'alerts_notification',
                'ordering': ['-sent_at'],
            },
        ),
        migrations.AddIndex(
            model_name='alert',
            index=models.Index(fields=['device', 'status'], name='alerts_alert_device_id_status_idx'),
        ),
        migrations.AddIndex(
            model_name='alert',
            index=models.Index(fields=['severity', '-created_at'], name='alerts_alert_severity_created_at_idx'),
        ),
        migrations.AddIndex(
            model_name='alert',
            index=models.Index(fields=['-created_at'], name='alerts_alert_created_at_idx'),
        ),
    ]
