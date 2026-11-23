import datetime
import json
import logging
import re
import secrets

import razorpay
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from bookings.models import Booking
from bookings.services import cancel_and_release
from .models import Payment
from .services import mark_paid
from .utils import get_razorpay_client

logger = logging.getLogger(__name__)

DEMO_BANKS = ["State Bank of India", "HDFC Bank", "ICICI Bank", "Axis Bank", "Punjab National Bank", "Kotak Mahindra Bank"]
DEMO_WALLETS = ["Paytm", "PhonePe", "Amazon Pay", "MobiKwik"]
TEST_CARD = "4111 1111 1111 1111"


def luhn_ok(number):
    total = 0
    for i, ch in enumerate(reversed(number)):
        d = int(ch)
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def validate_demo_payment(post):
    method = post.get("method", "")
    if method == "upi":
        upi = post.get("upi", "").strip()
        if not re.fullmatch(r"[\w.\-]{2,}@[a-zA-Z]{2,}", upi):
            return "", "Enter a valid UPI ID, for example name@upi."
        return f"UPI ({upi})", ""
    if method == "card":
        number = re.sub(r"\s", "", post.get("card_number", ""))
        if not (number.isdigit() and 13 <= len(number) <= 19 and luhn_ok(number)):
            return "", "That card number isn't valid. Use the test card shown on the page."
        m = re.fullmatch(r"(\d{2})\s*/\s*(\d{2})", post.get("expiry", "").strip())
        today = timezone.localdate()
        if not m or not 1 <= int(m.group(1)) <= 12 or (2000 + int(m.group(2)), int(m.group(1))) < (today.year, today.month):
            return "", "The card expiry date is invalid or in the past."
        if not re.fullmatch(r"\d{3,4}", post.get("cvv", "").strip()):
            return "", "Enter the 3 or 4 digit CVV."
        if not post.get("card_name", "").strip():
            return "", "Enter the name on the card."
        return f"Card ending {number[-4:]}", ""
    if method == "netbanking":
        bank = post.get("bank", "")
        if bank not in DEMO_BANKS:
            return "", "Please choose your bank."
        return f"Net banking ({bank})", ""
    if method == "wallet":
        wallet = post.get("wallet", "")
        if wallet not in DEMO_WALLETS:
            return "", "Please choose a wallet."
        return f"Wallet ({wallet})", ""
    return "", "Please choose a payment method."


@login_required
def checkout(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id, customer=request.user)

    if booking.status != Booking.Status.PENDING:
        return redirect("bookings:my_bookings")
    if booking.is_expired:
        cancel_and_release(booking, "expired")
        messages.error(request, "Your hold expired because payment wasn't completed in time. Please book again.")
        return redirect("services:detail", pk=booking.service_id)

    if settings.PAYMENT_MODE == "demo":
        payment, _ = Payment.objects.get_or_create(
            booking=booking,
            defaults={"amount": booking.total_price, "razorpay_order_id": f"order_demo_{secrets.token_hex(6)}"},
        )
        if not payment.razorpay_order_id:
            payment.razorpay_order_id = f"order_demo_{secrets.token_hex(6)}"
            payment.save(update_fields=["razorpay_order_id"])
        return render(request, "bookings/checkout_demo.html", {
            "booking": booking, "payment": payment, "expires_at": booking.expires_at,
            "banks": DEMO_BANKS, "wallets": DEMO_WALLETS, "test_card": TEST_CARD,
            "expiry_example": (timezone.localdate() + datetime.timedelta(days=730)).strftime("%m/%y"),
            "retry": payment.status == Payment.Status.FAILED,
        })

    amount_paise = int(booking.total_price * 100)
    payment, created = Payment.objects.get_or_create(
        booking=booking,
        defaults={"amount": booking.total_price, "razorpay_order_id": ""},
    )

    if created or not payment.razorpay_order_id:
        try:
            order = get_razorpay_client().order.create({
                "amount": amount_paise,
                "currency": "INR",
                "receipt": f"booking_{booking.id}",
                "notes": {"booking_id": str(booking.id)},
                "payment_capture": 1,
            })
        except Exception:
            logger.exception("Razorpay order creation failed for booking %s", booking.id)
            messages.error(request, "Payment service is unavailable right now. Please try again in a minute.")
            return redirect("bookings:my_bookings")
        payment.razorpay_order_id = order["id"]
        payment.save(update_fields=["razorpay_order_id"])

    return render(request, "bookings/checkout.html", {
        "booking": booking,
        "payment": payment,
        "razorpay_key": settings.RAZORPAY_KEY_ID,
        "amount_paise": amount_paise,
        "expires_at": booking.expires_at,
    })


@login_required
@require_POST
def demo_pay(request, booking_id):
    if settings.PAYMENT_MODE != "demo":
        raise Http404
    booking = get_object_or_404(Booking, pk=booking_id, customer=request.user)
    payment = get_object_or_404(Payment, booking=booking)
    if booking.status != Booking.Status.PENDING:
        return redirect("bookings:my_bookings")
    if booking.is_expired:
        cancel_and_release(booking, "expired")
        messages.error(request, "Your hold expired because payment wasn't completed in time. Please book again.")
        return redirect("services:detail", pk=booking.service_id)

    label, error = validate_demo_payment(request.POST)
    if error:
        messages.error(request, error)
        return redirect("payments:checkout", booking_id=booking.id)

    if request.POST.get("simulate_fail"):
        Payment.objects.filter(pk=payment.pk).exclude(status=Payment.Status.PAID).update(status=Payment.Status.FAILED, method=label)
        return redirect("payments:failed", booking_id=booking.id)

    status = mark_paid(payment.razorpay_order_id, f"pay_demo_{secrets.token_hex(7)}", "demo")
    Payment.objects.filter(pk=payment.pk).update(method=label)
    if status == Booking.Status.CONFIRMED:
        return redirect("payments:success", booking_id=booking.id)
    messages.error(request, "Your payment arrived after the hold expired, so it has been refunded.")
    return redirect("payments:failed", booking_id=booking.id)


@login_required
def payment_history(request):
    user = request.user
    base = Payment.objects.select_related("booking", "booking__service", "booking__customer")
    if user.is_provider:
        rows = base.filter(booking__service__provider=user)
    else:
        rows = base.filter(booking__customer=user)
    rows = rows.order_by("-created_at")
    paid = rows.filter(status=Payment.Status.PAID).aggregate(t=Sum("amount"))["t"] or 0
    refunded = rows.filter(status=Payment.Status.REFUNDED).aggregate(t=Sum("amount"))["t"] or 0
    return render(request, "bookings/payment_history.html", {
        "rows": rows[:100], "paid": paid, "refunded": refunded, "as_owner": user.is_provider,
    })


@login_required
@require_POST
def verify_payment(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id, customer=request.user)
    payment = get_object_or_404(Payment, booking=booking)

    params = {
        "razorpay_order_id": request.POST.get("razorpay_order_id", ""),
        "razorpay_payment_id": request.POST.get("razorpay_payment_id", ""),
        "razorpay_signature": request.POST.get("razorpay_signature", ""),
    }
    if not all(params.values()) or params["razorpay_order_id"] != payment.razorpay_order_id:
        return redirect("payments:failed", booking_id=booking.id)

    try:
        get_razorpay_client().utility.verify_payment_signature(params)
    except razorpay.errors.SignatureVerificationError:
        if payment.status == Payment.Status.CREATED:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status"])
        return redirect("payments:failed", booking_id=booking.id)

    status = mark_paid(params["razorpay_order_id"], params["razorpay_payment_id"], params["razorpay_signature"])
    if status == Booking.Status.CONFIRMED:
        return redirect("payments:success", booking_id=booking.id)
    messages.error(request, "Your payment arrived after the slot hold expired, so it is being refunded.")
    return redirect("payments:failed", booking_id=booking.id)


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    secret = settings.RAZORPAY_WEBHOOK_SECRET
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not secret or not signature:
        return HttpResponse(status=400)
    body = request.body.decode("utf-8", errors="replace")
    try:
        get_razorpay_client().utility.verify_webhook_signature(body, signature, secret)
    except razorpay.errors.SignatureVerificationError:
        return HttpResponse(status=400)

    try:
        event = json.loads(body)
        if event.get("event") in ("payment.captured", "order.paid"):
            entity = event["payload"]["payment"]["entity"]
            mark_paid(entity["order_id"], entity["id"])
    except (ValueError, KeyError, TypeError):
        logger.warning("Unrecognised Razorpay webhook payload")
    return HttpResponse(status=200)


@login_required
def payment_success(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id, customer=request.user)
    if booking.status != Booking.Status.CONFIRMED:
        return redirect("bookings:my_bookings")
    return render(request, "bookings/payment_success.html", {"booking": booking})


@login_required
def payment_failed(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id, customer=request.user)
    return render(request, "bookings/payment_failed.html", {"booking": booking})
