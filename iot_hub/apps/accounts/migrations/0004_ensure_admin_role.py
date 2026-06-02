from django.db import migrations


def ensure_admin_role_and_profiles(apps, schema_editor):
    """Ensure admin user has UserRole=admin and all users have profiles."""
    User = apps.get_model('auth', 'User')
    UserRole = apps.get_model('accounts', 'UserRole')
    UserProfile = apps.get_model('accounts', 'UserProfile')

    for user in User.objects.all():
        UserProfile.objects.get_or_create(user=user)
        role, _ = UserRole.objects.get_or_create(user=user, defaults={'role': 'client'})
        if user.is_superuser and role.role != 'admin':
            role.role = 'admin'
            role.save()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_create_user_profiles'),
    ]

    operations = [
        migrations.RunPython(ensure_admin_role_and_profiles, migrations.RunPython.noop),
    ]
