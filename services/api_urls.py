from django.urls import path
from .api_views import ServiceListAPIView, SlotListAPIView

urlpatterns = [
    path("services/", ServiceListAPIView.as_view(), name="api_service_list"),
    path("services/<int:service_id>/slots/", SlotListAPIView.as_view(), name="api_slot_list"),
]
