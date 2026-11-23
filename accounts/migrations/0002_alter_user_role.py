
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(choices=[('CUSTOMER', 'Kirayedaar / Tenant (looking for a room)'), ('PROVIDER', 'Makan Maalik / Owner (listing a room)')], default='CUSTOMER', max_length=20),
        ),
    ]
