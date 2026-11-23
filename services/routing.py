from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r"^ws/availability/(?P<service_id>\d+)/$", consumers.AvailabilityConsumer.as_asgi()),
]
