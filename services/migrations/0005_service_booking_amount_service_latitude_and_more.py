
import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0004_remove_service_duration_minutes_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='service',
            name='booking_amount',
            field=models.DecimalField(decimal_places=2, default=500, help_text='Token amount a tenant pays to reserve a visit (₹). Use 0 for free visits.', max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal('0'))]),
        ),
        migrations.AddField(
            model_name='service',
            name='latitude',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True, validators=[django.core.validators.MinValueValidator(Decimal('-90')), django.core.validators.MaxValueValidator(Decimal('90'))]),
        ),
        migrations.AddField(
            model_name='service',
            name='longitude',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True, validators=[django.core.validators.MinValueValidator(Decimal('-180')), django.core.validators.MaxValueValidator(Decimal('180'))]),
        ),
        migrations.AddField(
            model_name='service',
            name='whatsapp_number',
            field=models.CharField(blank=True, help_text="Optional. If you add it, it's shown publicly as a 'Chat on WhatsApp' button.", max_length=15),
        ),
        migrations.AlterField(
            model_name='review',
            name='rating',
            field=models.PositiveSmallIntegerField(default=5, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)]),
        ),
        migrations.CreateModel(
            name='ServiceImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(upload_to='services/')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('service', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='images', to='services.service')),
            ],
            options={
                'ordering': ['id'],
            },
        ),
        migrations.CreateModel(
            name='Report',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reason', models.CharField(choices=[('SCAM', 'Looks like a scam / asks for money outside the app'), ('WRONG_INFO', 'Wrong price, photos or details'), ('UNAVAILABLE', 'Room is no longer available'), ('INAPPROPRIATE', 'Inappropriate content'), ('OTHER', 'Something else')], max_length=20)),
                ('details', models.TextField(blank=True)),
                ('resolved', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('reporter', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reports', to=settings.AUTH_USER_MODEL)),
                ('service', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reports', to='services.service')),
            ],
            options={
                'ordering': ['resolved', '-created_at'],
                'unique_together': {('service', 'reporter')},
            },
        ),
    ]
