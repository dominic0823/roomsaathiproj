from rest_framework import serializers
from .models import Category, Service, Slot


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "icon"]


class SlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = Slot
        fields = ["id", "date", "start_time", "end_time", "is_booked"]


class ServiceSerializer(serializers.ModelSerializer):
    provider_name = serializers.CharField(source="provider.username", read_only=True)
    owner_verified = serializers.BooleanField(source="provider.is_verified", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    cover_image = serializers.SerializerMethodField()
    open_slots = serializers.SerializerMethodField()
    amenity_names = serializers.SerializerMethodField()
    beds_left = serializers.IntegerField(read_only=True)

    class Meta:
        model = Service
        fields = [
            "id", "title", "description", "price", "deposit_amount", "booking_amount",
            "advance_amount", "total_beds", "beds_left", "gender_allowed", "amenity_names",
            "min_stay_months", "is_furnished", "tenant_preference", "city", "location",
            "latitude", "longitude", "cover_image", "is_active",
            "provider_name", "owner_verified", "category_name", "open_slots",
        ]

    def get_cover_image(self, obj):
        url = obj.cover_url
        request = self.context.get("request")
        return request.build_absolute_uri(url) if (url and request) else url or None

    def get_open_slots(self, obj):
        return SlotSerializer(obj.open_slots()[:20], many=True).data

    def get_amenity_names(self, obj):
        return [a.name for a in obj.amenities.all()]
