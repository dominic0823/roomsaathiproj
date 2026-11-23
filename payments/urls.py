from django.urls import path
from . import views

app_name = "payments"

urlpatterns = [
    path("checkout/<int:booking_id>/", views.checkout, name="checkout"),
    path("verify/<int:booking_id>/", views.verify_payment, name="verify"),
    path("demo-pay/<int:booking_id>/", views.demo_pay, name="demo_pay"),
    path("history/", views.payment_history, name="history"),
    path("success/<int:booking_id>/", views.payment_success, name="success"),
    path("failed/<int:booking_id>/", views.payment_failed, name="failed"),
    path("webhook/", views.razorpay_webhook, name="webhook"),
]
