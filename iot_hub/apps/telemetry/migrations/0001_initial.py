from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('devices', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Telemetry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('value', models.FloatField()),
                ('unit', models.CharField(blank=True, max_length=50)),
                ('status', models.CharField(choices=[('ok', 'OK'), ('warning', 'Warning'), ('error', 'Error')], default='ok', max_length=20)),
                ('raw_data', models.JSONField(blank=True, default=dict)),
                ('recorded_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='telemetry', to='devices.device')),
                ('metric', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='readings', to='devices.devicemetric')),
            ],
            options={
                'verbose_name': 'Телеметрия',
                'verbose_name_plural': 'Телеметрии',
                'db_table': 'telemetry_telemetry',
                'ordering': ['-recorded_at'],
            },
        ),
        migrations.CreateModel(
            name='TelemetryStatistics',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('count', models.IntegerField(default=0)),
                ('min_value', models.FloatField(blank=True, null=True)),
                ('max_value', models.FloatField(blank=True, null=True)),
                ('avg_value', models.FloatField(blank=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('metric', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='statistics', to='devices.devicemetric')),
            ],
            options={
                'verbose_name': 'Статистика телеметрии',
                'verbose_name_plural': 'Статистика телеметрии',
                'db_table': 'telemetry_statistics',
            },
        ),
        migrations.CreateModel(
            name='TelemetryBatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('data', models.JSONField()),
                ('count', models.IntegerField()),
                ('processed', models.BooleanField(default=False)),
                ('received_at', models.DateTimeField(auto_now_add=True)),
                ('processed_at', models.DateTimeField(blank=True, null=True)),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='telemetry_batches', to='devices.device')),
            ],
            options={
                'verbose_name': 'Пакет телеметрии',
                'verbose_name_plural': 'Пакеты телеметрии',
                'db_table': 'telemetry_telemetrybatch',
                'ordering': ['-received_at'],
            },
        ),
        migrations.AddIndex(
            model_name='telemetry',
            index=models.Index(fields=['device', '-recorded_at'], name='telemetry_t_device_id_recorded_at_idx'),
        ),
        migrations.AddIndex(
            model_name='telemetry',
            index=models.Index(fields=['metric', '-recorded_at'], name='telemetry_t_metric_id_recorded_at_idx'),
        ),
        migrations.AddIndex(
            model_name='telemetry',
            index=models.Index(fields=['recorded_at'], name='telemetry_t_recorded_at_idx'),
        ),
    ]
