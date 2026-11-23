
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0008_service_city_service_view_count_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='serviceimage',
            name='image_url',
            field=models.URLField(blank=True, max_length=600),
        ),
        migrations.AddField(
            model_name='serviceimage',
            name='is_360',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='serviceimage',
            name='image',
            field=models.ImageField(blank=True, null=True, upload_to='services/'),
        ),
    ]
