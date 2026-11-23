
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_user_email_verified_user_phone_verified_notification_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='otpcode',
            name='channel',
            field=models.CharField(choices=[('PHONE', 'Phone (SMS)'), ('WHATSAPP', 'WhatsApp'), ('EMAIL', 'Email')], max_length=10),
        ),
    ]
