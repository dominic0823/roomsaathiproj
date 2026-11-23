import calendar
import datetime
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from services.models import Service
from services.realtime import broadcast_slot
from .models import Booking
from .tasks import queue_notification

B = Booking.Status


class BookingError(Exception):
    pass


def add_months(d, months):
    year, month0 = divmod(d.month - 1 + months, 12)
    year, month = d.year + year, month0 + 1
    return datetime.date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


@transaction.atomic
def cancel_and_release(booking, event="cancelled"):
    booking = Booking.objects.select_for_update().select_related("slot").get(pk=booking.pk)
    if booking.status in (B.CANCELLED, B.DECLINED):
        return False
    booking.status = B.CANCELLED
    booking.save(update_fields=["status"])

    slot = booking.slot
    if slot is not None:
        slot.is_booked = False
        slot.save(update_fields=["is_booked"])
        transaction.on_commit(lambda: broadcast_slot(slot))
    transaction.on_commit(lambda: queue_notification(booking.id, event))
    return True


def create_rental_request(tenant, service, move_in, months, note=""):
    today = timezone.localdate()
    end = add_months(move_in, months)
    with transaction.atomic():
        room = Service.objects.select_for_update().get(pk=service.pk)
        if not room.is_active:
            raise BookingError("This listing is no longer available.")
        if room.provider_id == tenant.id:
            raise BookingError("You can't book your own room.")
        if Booking.objects.filter(
            customer=tenant, service=room, kind=Booking.Kind.RENTAL,
            status__in=[B.REQUESTED, B.PENDING, B.CONFIRMED], stay_end_date__gt=today,
        ).exists():
            raise BookingError("You already have an active request or booking for this room.")
        if room.beds_left_between(move_in, end) <= 0:
            raise BookingError("Sorry, this room is fully booked for those dates.")
        booking = Booking.objects.create(
            kind=Booking.Kind.RENTAL, customer=tenant, service=room, status=B.REQUESTED,
            total_price=room.advance_amount, move_in_date=move_in, stay_months=months,
            stay_end_date=end, tenant_note=note[:500], monthly_rent=room.price,
            deposit_amount=room.deposit_amount,
        )
        transaction.on_commit(lambda: queue_notification(booking.id, "rental_requested"))
    return booking


def approve_rental(booking, owner_note=""):
    with transaction.atomic():
        b = Booking.objects.select_for_update().get(pk=booking.pk)
        if not b.is_rental or b.status != B.REQUESTED:
            raise BookingError("This request has already been handled.")
        if b.is_expired:
            raise BookingError("This request expired. The tenant can send a new one.")
        room = Service.objects.select_for_update().get(pk=b.service_id)
        if room.beds_left_between(b.move_in_date, b.stay_end_date) <= 0:
            raise BookingError("No bed is free for those dates - decline this request or free up a bed first.")
        b.owner_note = owner_note[:500]
        b.approved_at = timezone.now()
        if b.total_price <= 0:
            b.status = B.CONFIRMED
            event = "confirmed"
        else:
            b.status = B.PENDING
            event = "rental_approved"
        b.save()
        transaction.on_commit(lambda: queue_notification(b.id, event))
    return b


def decline_rental(booking, owner_note=""):
    with transaction.atomic():
        b = Booking.objects.select_for_update().get(pk=booking.pk)
        if not b.is_rental or b.status != B.REQUESTED:
            raise BookingError("This request has already been handled.")
        b.status = B.DECLINED
        b.owner_note = owner_note[:500]
        b.save(update_fields=["status", "owner_note"])
        transaction.on_commit(lambda: queue_notification(b.id, "rental_declined"))
    return b


def expire_stale_pending():
    now = timezone.now()
    count = 0
    visits = Booking.objects.filter(
        kind=Booking.Kind.VISIT, status=B.PENDING,
        created_at__lt=now - timedelta(minutes=settings.PENDING_BOOKING_MINUTES),
    )
    pay_cut = now - timedelta(hours=settings.RENTAL_PAYMENT_HOURS)
    unpaid_rentals = Booking.objects.filter(kind=Booking.Kind.RENTAL, status=B.PENDING).filter(
        Q(approved_at__lt=pay_cut) | Q(approved_at__isnull=True, created_at__lt=pay_cut)
    )
    old_requests = Booking.objects.filter(
        kind=Booking.Kind.RENTAL, status=B.REQUESTED,
        created_at__lt=now - timedelta(hours=settings.RENTAL_REQUEST_HOURS),
    )
    for qs, event in ((visits, "expired"), (unpaid_rentals, "expired"), (old_requests, "request_expired")):
        for booking in qs:
            if cancel_and_release(booking, event):
                count += 1
    return count
