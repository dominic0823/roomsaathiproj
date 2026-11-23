from django.db import migrations

DEFAULTS = [
    ("Wi-Fi", "📶"), ("AC", "❄️"), ("Attached bathroom", "🚿"), ("Meals included", "🍛"),
    ("Laundry", "🧺"), ("Parking", "🅿️"), ("Power backup", "🔋"), ("Geyser / hot water", "♨️"),
    ("CCTV & security", "📹"), ("Study table", "📚"), ("Housekeeping", "🧹"), ("Lift", "🛗"),
]


def add_amenities(apps, schema_editor):
    Amenity = apps.get_model("services", "Amenity")
    for name, icon in DEFAULTS:
        Amenity.objects.get_or_create(name=name, defaults={"icon": icon})


class Migration(migrations.Migration):
    dependencies = [("services", "0006_amenity_service_advance_amount_and_more")]
    operations = [migrations.RunPython(add_amenities, migrations.RunPython.noop)]
