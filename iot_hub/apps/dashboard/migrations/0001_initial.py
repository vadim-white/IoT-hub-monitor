from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='DashboardSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('widgets', models.JSONField(blank=True, default=list)),
                ('theme', models.CharField(choices=[('light', 'Светлая'), ('dark', 'Темная')], default='light', max_length=20)),
                ('auto_refresh_interval', models.IntegerField(default=30)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='dashboard_settings', to='auth.user')),
            ],
            options={
                'verbose_name': 'Настройки дашборда',
                'verbose_name_plural': 'Настройки дашбордов',
                'db_table': 'dashboard_settings',
            },
        ),
    ]
