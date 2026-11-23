from django.urls import path
from .api_views import MyBookingsAPIView

urlpatterns = [
    path("bookings/mine/", MyBookingsAPIView.as_view(), name="api_my_bookings"),
]
