
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0002_alter_booking_slot_and_more'),
        ('services', '0006_amenity_service_advance_amount_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='booking',
            name='unique_active_booking_per_slot',
        ),
        migrations.AddField(
            model_name='booking',
            name='approved_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='booking',
            name='deposit_amount',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='booking',
            name='kind',
            field=models.CharField(choices=[('VISIT', 'Visit'), ('RENTAL', 'Room booking')], default='VISIT', max_length=10),
        ),
        migrations.AddField(
            model_name='booking',
            name='monthly_rent',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='booking',
            name='move_in_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='booking',
            name='owner_note',
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name='booking',
            name='stay_end_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='booking',
            name='stay_months',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='booking',
            name='tenant_note',
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AlterField(
            model_name='booking',
            name='slot',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='bookings', to='services.slot'),
        ),
        migrations.AlterField(
            model_name='booking',
            name='status',
            field=models.CharField(choices=[('REQUESTED', 'Awaiting owner approval'), ('PENDING', 'Pending payment'), ('CONFIRMED', 'Confirmed'), ('DECLINED', 'Declined by owner'), ('CANCELLED', 'Cancelled')], default='PENDING', max_length=20),
        ),
        migrations.AlterField(
            model_name='booking',
            name='total_price',
            field=models.DecimalField(decimal_places=2, help_text='Amount payable online (token / advance)', max_digits=10),
        ),
        migrations.AddConstraint(
            model_name='booking',
            constraint=models.UniqueConstraint(condition=models.Q(('slot__isnull', False), models.Q(('status__in', ['CANCELLED', 'DECLINED']), _negated=True)), fields=('slot',), name='unique_active_booking_per_slot'),
        ),
        migrations.AddConstraint(
            model_name='booking',
            constraint=models.CheckConstraint(check=models.Q(('kind', 'RENTAL'), ('slot__isnull', False), _connector='OR'), name='visit_booking_needs_slot'),
        ),
    ]
