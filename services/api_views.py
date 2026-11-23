from django.db.models import Q
from rest_framework import generics, permissions
from .models import Service, Slot
from .serializers import ServiceSerializer, SlotSerializer


class ServiceListAPIView(generics.ListAPIView):

    serializer_class = ServiceSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = (Service.objects.filter(is_active=True)
              .select_related("provider", "category").prefetch_related("images", "amenities").order_by("-created_at"))
        p = self.request.query_params
        if p.get("q"):
            qs = qs.filter(Q(title__icontains=p["q"]) | Q(location__icontains=p["q"]))
        if p.get("min_price"):
            try:
                qs = qs.filter(price__gte=p["min_price"])
            except (ValueError, ArithmeticError):
                pass
        if p.get("max_price"):
            try:
                qs = qs.filter(price__lte=p["max_price"])
            except (ValueError, ArithmeticError):
                pass
        if p.get("pref") in Service.TenantPreference.values:
            qs = qs.filter(Q(tenant_preference=p["pref"]) | Q(tenant_preference="ANYONE"))
        if p.get("furnished") == "1":
            qs = qs.filter(is_furnished=True)
        return qs


class SlotListAPIView(generics.ListAPIView):
    serializer_class = SlotSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        service = Service.objects.filter(pk=self.kwargs["service_id"], is_active=True).first()
        return service.open_slots() if service else Slot.objects.none()
