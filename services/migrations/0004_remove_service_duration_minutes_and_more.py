
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0003_alter_service_category'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='service',
            name='duration_minutes',
        ),
        migrations.AddField(
            model_name='service',
            name='deposit_amount',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Refundable security deposit (₹)', max_digits=10),
        ),
        migrations.AddField(
            model_name='service',
            name='is_furnished',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='service',
            name='min_stay_months',
            field=models.PositiveIntegerField(default=1, help_text='Minimum stay required, in months'),
        ),
        migrations.AddField(
            model_name='service',
            name='tenant_preference',
            field=models.CharField(choices=[('ANYONE', 'Anyone'), ('STUDENT', 'Students'), ('FAMILY', 'Family'), ('DEFENCE', 'Defence / Army personnel'), ('WORKING_PROFESSIONAL', 'Working professionals')], default='ANYONE', max_length=25),
        ),
        migrations.AlterField(
            model_name='service',
            name='price',
            field=models.DecimalField(decimal_places=2, help_text='Monthly rent (₹)', max_digits=10),
        ),
    ]
