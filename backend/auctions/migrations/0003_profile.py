from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('auctions', '0002_signup_quantity'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Profile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('phone', models.CharField(blank=True, max_length=40)),
                ('address_line1', models.CharField(blank=True, max_length=200, verbose_name='Address line 1')),
                ('address_line2', models.CharField(blank=True, max_length=200, verbose_name='Address line 2')),
                ('city', models.CharField(blank=True, max_length=100)),
                ('state', models.CharField(blank=True, max_length=100)),
                ('postal_code', models.CharField(blank=True, max_length=20)),
                ('country', models.CharField(blank=True, max_length=100)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profile', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
