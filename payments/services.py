from django.db import transaction

from bookings.models import Booking
from bookings.tasks import queue_notification
from .models import Payment
from .utils import refund_booking_payment


def mark_paid(order_id, payment_id, signature=""):
    with transaction.atomic():
        payment = (
            Payment.objects.select_for_update().select_related("booking")
            .filter(razorpay_order_id=order_id).first()
        )
        if payment is None:
            return None
        booking = payment.booking
        if payment.status in (Payment.Status.PAID, Payment.Status.REFUNDED):
            return booking.status

        payment.razorpay_payment_id = payment_id
        payment.razorpay_signature = signature
        payment.status = Payment.Status.PAID
        payment.save()

        if booking.status == Booking.Status.PENDING:
            booking.status = Booking.Status.CONFIRMED
            booking.save(update_fields=["status"])
            transaction.on_commit(lambda: queue_notification(booking.id, "confirmed"))
            return booking.status
        late = True

    if late:
        refund_booking_payment(booking)
    return booking.status
