from django.db import migrations
import os


def create_superuser(apps, schema_editor):
    from django.contrib.auth import get_user_model
    User = get_user_model()

    email = os.environ.get('DJANGO_SUPERUSER_EMAIL', '')
    password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '')

    if email and password and not User.objects.filter(email=email).exists():
        User.objects.create_superuser(
            email=email,
            password=password,
            first_name='Admin',
            last_name='Admin',
            is_verified=True,
        )


def delete_superuser(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_superuser, delete_superuser),
    ]