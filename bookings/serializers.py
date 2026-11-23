from rest_framework import serializers
from .models import Booking


class BookingSerializer(serializers.ModelSerializer):
    service_title = serializers.CharField(source="service.title", read_only=True)
    slot_date = serializers.DateField(source="slot.date", read_only=True)
    slot_time = serializers.TimeField(source="slot.start_time", read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id", "service", "service_title", "slot", "slot_date", "slot_time",
            "status", "total_price", "created_at",
        ]
        read_only_fields = ["status", "total_price"]
