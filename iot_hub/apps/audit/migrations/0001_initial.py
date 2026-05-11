from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('create', 'Создание'), ('update', 'Обновление'), ('delete', 'Удаление'), ('login', 'Вход'), ('logout', 'Выход'), ('threshold_change', 'Изменение порога'), ('alert_action', 'Действие с алертом'), ('device_action', 'Действие с устройством'), ('export', 'Экспорт'), ('import', 'Импорт'), ('config_change', 'Изменение конфигурации')], max_length=50)),
                ('object_id', models.PositiveIntegerField(blank=True, null=True)),
                ('object_repr', models.CharField(blank=True, max_length=255)),
                ('changes', models.JSONField(blank=True, default=dict)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.TextField(blank=True)),
                ('timestamp', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('actor', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='audit_logs', to='auth.user')),
                ('content_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='contenttypes.contenttype')),
            ],
            options={
                'verbose_name': 'Запись аудита',
                'verbose_name_plural': 'Записи аудита',
                'db_table': 'audit_auditlog',
                'ordering': ['-timestamp'],
            },
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['actor', '-timestamp'], name='audit_audit_actor_id_timestamp_idx'),
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['action', '-timestamp'], name='audit_audit_action_timestamp_idx'),
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['content_type', 'object_id'], name='audit_audit_contenttypes_app_object_id_idx'),
        ),
    ]
