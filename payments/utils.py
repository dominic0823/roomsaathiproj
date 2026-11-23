import logging
import secrets

import razorpay
from django.conf import settings

logger = logging.getLogger(__name__)


def get_razorpay_client():
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def refund_booking_payment(booking):
    from .models import Payment

    payment = Payment.objects.filter(booking=booking).first()
    if payment is None or payment.status == Payment.Status.REFUNDED:
        return payment is not None
    if payment.status != Payment.Status.PAID or not payment.razorpay_payment_id:
        return False
    if payment.razorpay_order_id.startswith("order_demo_"):
        payment.razorpay_refund_id = f"rfnd_demo_{secrets.token_hex(6)}"
        payment.status = Payment.Status.REFUNDED
        payment.save(update_fields=["razorpay_refund_id", "status"])
        return True
    try:
        refund = get_razorpay_client().payment.refund(
            payment.razorpay_payment_id, {"amount": int(payment.amount * 100)}
        )
    except Exception:
        logger.exception("Refund failed for payment %s", payment.pk)
        return False
    payment.razorpay_refund_id = refund.get("id", "")
    payment.status = Payment.Status.REFUNDED
    payment.save(update_fields=["razorpay_refund_id", "status"])
    return True
