from django.urls import path
from . import views

app_name = "chatapp"

urlpatterns = [
    path("", views.inbox, name="inbox"),
    path("<int:booking_id>/", views.chat_room, name="room"),
]
