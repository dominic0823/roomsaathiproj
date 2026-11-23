
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_alter_user_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='is_verified',
            field=models.BooleanField(default=False, help_text="Shown as a 'Verified owner' badge on listings."),
        ),
        migrations.AddField(
            model_name='user',
            name='verification_note',
            field=models.TextField(blank=True, help_text="Owner's note for the verification team."),
        ),
        migrations.AddField(
            model_name='user',
            name='verification_requested',
            field=models.BooleanField(default=False),
        ),
    ]
