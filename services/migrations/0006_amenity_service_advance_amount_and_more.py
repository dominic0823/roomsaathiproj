
import django.core.validators
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0005_service_booking_amount_service_latitude_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Amenity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=60, unique=True)),
                ('icon', models.CharField(blank=True, max_length=8)),
            ],
            options={
                'verbose_name_plural': 'Amenities',
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='service',
            name='advance_amount',
            field=models.DecimalField(decimal_places=2, default=2000, help_text='Advance a tenant pays online to reserve the room (adjusted against first rent). 0 = no advance.', max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal('0'))]),
        ),
        migrations.AddField(
            model_name='service',
            name='gender_allowed',
            field=models.CharField(choices=[('ANY', 'Anyone'), ('MALE', 'Boys / Men only'), ('FEMALE', 'Girls / Women only')], default='ANY', max_length=6),
        ),
        migrations.AddField(
            model_name='service',
            name='total_beds',
            field=models.PositiveIntegerField(default=1, help_text='How many tenants can stay (1 for a private room, more for a PG/shared room)', validators=[django.core.validators.MinValueValidator(1)]),
        ),
        migrations.AddField(
            model_name='service',
            name='amenities',
            field=models.ManyToManyField(blank=True, related_name='services', to='services.amenity'),
        ),
    ]
