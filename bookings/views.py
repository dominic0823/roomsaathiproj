from django.contrib import messages
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import phone_verified_required
from payments.utils import refund_booking_payment
from services.forms import ReviewForm
from services.models import Service, Slot
from services.realtime import broadcast_slot
from .forms import RentalRequestForm
from .models import Booking
from .services import (BookingError, approve_rental, cancel_and_release, create_rental_request,
                       decline_rental, expire_stale_pending)
from .tasks import queue_notification

MAX_PENDING_PER_TENANT = 3
S = Booking.Status


@phone_verified_required
@require_POST
def create_booking(request, slot_id):
    if not request.user.is_customer:
        messages.error(request, "Only tenant accounts can book visits.")
        return redirect("home")

    expire_stale_pending()

    if Booking.objects.filter(customer=request.user, kind=Booking.Kind.VISIT, status=S.PENDING).count() >= MAX_PENDING_PER_TENANT:
        messages.error(request, "You have several unpaid visit bookings. Pay or cancel one first.")
        return redirect("bookings:my_bookings")

    with transaction.atomic():
        slot = Slot.objects.select_for_update().filter(pk=slot_id).first()
        if slot is None:
            return redirect("services:list")
        service = slot.service
        if not service.is_active:
            messages.error(request, "This listing is no longer available.")
            return redirect("services:list")
        if slot.is_booked or slot.is_past:
            messages.error(request, "Sorry, that slot was just taken or has passed. Please pick another.")
            return redirect("services:detail", pk=service.pk)

        free = service.booking_amount <= 0
        booking = Booking.objects.create(
            kind=Booking.Kind.VISIT, customer=request.user, service=service, slot=slot,
            status=S.CONFIRMED if free else S.PENDING, total_price=service.booking_amount,
        )
        slot.is_booked = True
        slot.save(update_fields=["is_booked"])

        transaction.on_commit(lambda: broadcast_slot(slot))
        transaction.on_commit(lambda: queue_notification(booking.id, "confirmed" if free else "created"))

    if free:
        messages.success(request, "Visit confirmed! You can now chat with the owner.")
        return redirect("bookings:my_bookings")
    return redirect("payments:checkout", booking_id=booking.id)


@phone_verified_required
@require_POST
def rent_room(request, service_id):
    service = get_object_or_404(Service, pk=service_id, is_active=True)
    if not request.user.is_customer:
        messages.error(request, "Only tenant accounts can book a room.")
        return redirect("services:detail", pk=service.pk)
    expire_stale_pending()

    form = RentalRequestForm(request.POST, service=service)
    if not form.is_valid():
        first = next(iter(form.errors.values()))[0]
        messages.error(request, first)
        return redirect("services:detail", pk=service.pk)
    try:
        create_rental_request(
            request.user, service, form.cleaned_data["move_in_date"],
            form.cleaned_data["stay_months"], form.cleaned_data["note"],
        )
    except BookingError as exc:
        messages.error(request, str(exc))
        return redirect("services:detail", pk=service.pk)
    messages.success(request, "Request sent to the owner! You'll get a notification when they respond.")
    return redirect("bookings:my_bookings")


def _owner_booking(request, booking_id):
    return get_object_or_404(
        Booking.objects.select_related("service", "slot", "customer"),
        pk=booking_id, service__provider=request.user,
    )


@login_required
@require_POST
def approve_booking(request, booking_id):
    booking = _owner_booking(request, booking_id)
    try:
        b = approve_rental(booking, request.POST.get("note", ""))
    except BookingError as exc:
        messages.error(request, str(exc))
    else:
        if b.status == S.CONFIRMED:
            messages.success(request, "Approved - the room is booked for this tenant.")
        else:
            messages.success(request, "Approved! The tenant now has "
                                      f"{request_hours()} hours to pay the advance.")
    return redirect("bookings:provider_bookings")


@login_required
@require_POST
def decline_booking(request, booking_id):
    booking = _owner_booking(request, booking_id)
    try:
        decline_rental(booking, request.POST.get("note", ""))
    except BookingError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Request declined.")
    return redirect("bookings:provider_bookings")


@login_required
@require_POST
def owner_cancel_booking(request, booking_id):
    booking = _owner_booking(request, booking_id)
    if booking.status != S.CONFIRMED:
        messages.error(request, "Only confirmed bookings can be cancelled here.")
        return redirect("bookings:provider_bookings")
    if cancel_and_release(booking, "owner_cancelled"):
        if booking.total_price > 0 and not refund_booking_payment(booking):
            messages.warning(request, "Cancelled, but the automatic refund failed - please contact support to refund the tenant.")
        else:
            messages.success(request, "Booking cancelled and the tenant has been refunded.")
    return redirect("bookings:provider_bookings")


def request_hours():
    from django.conf import settings
    return settings.RENTAL_PAYMENT_HOURS


@login_required
def my_bookings(request):
    expire_stale_pending()
    bookings = (
        Booking.objects.filter(customer=request.user)
        .select_related("service", "slot", "service__provider").order_by("-created_at")
    )
    return render(request, "bookings/my_bookings.html", {"bookings": bookings})


@login_required
def provider_bookings(request):
    if not request.user.is_provider:
        return redirect("home")
    expire_stale_pending()
    bookings = list(
        Booking.objects.filter(service__provider=request.user)
        .select_related("service", "slot", "customer").order_by("-created_at")
    )
    needs_action = [b for b in bookings if b.status == S.REQUESTED]
    others = [b for b in bookings if b.status != S.REQUESTED]
    return render(request, "bookings/provider_bookings.html", {"needs_action": needs_action, "others": others})


@login_required
@require_POST
def cancel_booking(request, booking_id):
    booking = get_object_or_404(Booking.objects.select_related("slot"), pk=booking_id, customer=request.user)
    if booking.status in (S.CANCELLED, S.DECLINED):
        return redirect("bookings:my_bookings")
    if booking.status == S.CONFIRMED:
        if booking.is_rental and booking.move_in_date <= timezone.localdate():
            messages.error(request, "The stay has already started - please talk to the owner about ending it.")
            return redirect("bookings:my_bookings")
        if not booking.is_rental and booking.slot.is_past:
            messages.error(request, "This visit has already started, so it can't be cancelled.")
            return redirect("bookings:my_bookings")

    paid = booking.status == S.CONFIRMED and booking.total_price > 0
    eligible = booking.refund_eligible
    if cancel_and_release(booking, "cancelled"):
        if not paid:
            messages.success(request, "Booking cancelled.")
        elif eligible:
            if refund_booking_payment(booking):
                messages.success(request, "Booking cancelled. Your refund has been initiated.")
            else:
                messages.warning(request, "Booking cancelled. We couldn't start the refund automatically - our team will process it.")
        else:
            messages.warning(request, "Booking cancelled. As it's very close to move-in, the advance is non-refundable.")
    return redirect("bookings:my_bookings")


@login_required
def leave_review(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id, customer=request.user, status=S.CONFIRMED)
    if hasattr(booking, "review"):
        messages.info(request, "You've already reviewed this booking.")
        return redirect("bookings:my_bookings")
    if not booking.can_review:
        messages.info(request, "You can review after your visit / move-in date.")
        return redirect("bookings:my_bookings")

    if request.method == "POST":
        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.booking = booking
            review.service = booking.service
            review.customer = request.user
            review.save()
            messages.success(request, "Thanks for your review!")
            return redirect("bookings:my_bookings")
    else:
        form = ReviewForm()
    return render(request, "bookings/leave_review.html", {"booking": booking, "form": form})


@login_required
def receipt(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.select_related("service", "service__provider", "customer", "slot"), pk=booking_id
    )
    if request.user not in (booking.customer, booking.service.provider):
        return render(request, "chat/forbidden.html", status=403)
    if booking.status != S.CONFIRMED:
        messages.info(request, "A receipt is available once the booking is confirmed.")
        return redirect("bookings:my_bookings")
    return render(request, "bookings/receipt.html", {"booking": booking})


@login_required
def calendar_ics(request, booking_id):
    import datetime as dt
    booking = get_object_or_404(
        Booking.objects.select_related("service", "slot", "customer", "service__provider"), pk=booking_id
    )
    if request.user not in (booking.customer, booking.service.provider) or booking.status != S.CONFIRMED:
        return redirect("bookings:my_bookings")
    esc = lambda t: str(t).replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")
    stamp = timezone.now().strftime("%Y%m%dT%H%M%SZ")
    if booking.is_rental:
        start = f"DTSTART;VALUE=DATE:{booking.move_in_date:%Y%m%d}"
        end = f"DTEND;VALUE=DATE:{(booking.move_in_date + dt.timedelta(days=1)):%Y%m%d}"
        title = f"Move in: {booking.service.title}"
    else:
        slot = booking.slot
        start = f"DTSTART:{slot.starts_at.astimezone(dt.timezone.utc):%Y%m%dT%H%M%SZ}"
        end_dt = timezone.make_aware(dt.datetime.combine(slot.date, slot.end_time))
        end = f"DTEND:{end_dt.astimezone(dt.timezone.utc):%Y%m%dT%H%M%SZ}"
        title = f"Room visit: {booking.service.title}"
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//RoomSaathi//EN", "BEGIN:VEVENT",
             f"UID:booking-{booking.id}@roomsaathi", f"DTSTAMP:{stamp}", start, end,
             f"SUMMARY:{esc(title)}", f"LOCATION:{esc(booking.service.location + ', ' + booking.service.city)}",
             f"DESCRIPTION:{esc('Booked on RoomSaathi. Ref RS' + format(booking.id, '05d'))}", "END:VEVENT", "END:VCALENDAR"]
    response = HttpResponse("\r\n".join(lines) + "\r\n", content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="roomsaathi-booking-{booking.id}.ics"'
    return response
