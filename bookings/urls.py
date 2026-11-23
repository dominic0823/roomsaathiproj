from django.urls import path
from . import views

app_name = "bookings"

urlpatterns = [
    path("create/<int:slot_id>/", views.create_booking, name="create_booking"),
    path("rent/<int:service_id>/", views.rent_room, name="rent_room"),
    path("my/", views.my_bookings, name="my_bookings"),
    path("provider/", views.provider_bookings, name="provider_bookings"),
    path("cancel/<int:booking_id>/", views.cancel_booking, name="cancel_booking"),
    path("<int:booking_id>/approve/", views.approve_booking, name="approve_booking"),
    path("<int:booking_id>/decline/", views.decline_booking, name="decline_booking"),
    path("<int:booking_id>/owner-cancel/", views.owner_cancel_booking, name="owner_cancel_booking"),
    path("<int:booking_id>/calendar.ics", views.calendar_ics, name="calendar_ics"),
    path("<int:booking_id>/receipt/", views.receipt, name="receipt"),
    path("review/<int:booking_id>/", views.leave_review, name="leave_review"),
]
