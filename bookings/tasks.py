import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse

logger = logging.getLogger(__name__)


def queue_notification(booking_id, event):
    try:
        send_booking_notification.delay(booking_id, event)
    except Exception:
        logger.exception("Could not queue %s notification for booking %s", event, booking_id)


def _send(user, subject, body, url):
    from accounts.notifications import notify

    notify(user, subject, url)
    if user.email:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)


@shared_task
def send_booking_notification(booking_id, event):
    from .models import Booking

    try:
        b = Booking.objects.select_related("customer", "service", "service__provider", "slot").get(pk=booking_id)
    except Booking.DoesNotExist:
        return

    tenant, owner, room = b.customer, b.service.provider, b.service.title
    when = b.when_label
    to_tenant, to_owner = reverse("bookings:my_bookings"), reverse("bookings:provider_bookings")
    contact = f" Their phone: {tenant.phone_number}." if tenant.phone_number else ""
    rental = b.is_rental

    if event == "created":
        _send(tenant, f"Pay to hold your visit - {room}",
              f"Hi {tenant.username}, your visit to '{room}' ({when}) is on hold. Pay within "
              f"{settings.PENDING_BOOKING_MINUTES} minutes or the slot is released.", to_tenant)
        _send(owner, f"New visit request - {room}",
              f"Hi {owner.username}, {tenant.username} requested a visit ({when}). You'll be told once they pay.", to_owner)
    elif event == "rental_requested":
        _send(owner, f"New room request - {room}",
              f"Hi {owner.username}, {tenant.username} wants to rent '{room}' ({when}). "
              f"Please approve or decline within {settings.RENTAL_REQUEST_HOURS} hours.", to_owner)
        _send(tenant, f"Request sent - {room}",
              f"Hi {tenant.username}, your request for '{room}' ({when}) was sent to the owner. "
              f"You'll hear back within {settings.RENTAL_REQUEST_HOURS} hours.", to_tenant)
    elif event == "rental_approved":
        _send(tenant, f"Approved! Pay the advance - {room}",
              f"Hi {tenant.username}, the owner approved your request for '{room}' ({when}). "
              f"Pay the advance of Rs {b.total_price:.0f} within {settings.RENTAL_PAYMENT_HOURS} hours "
              f"to confirm the room. Owner's note: {b.owner_note or '-'}", to_tenant)
    elif event == "rental_declined":
        _send(tenant, f"Request declined - {room}",
              f"Hi {tenant.username}, the owner couldn't accept your request for '{room}' ({when}). "
              f"Note: {b.owner_note or '-'}. Plenty of other rooms are available.", to_tenant)
    elif event == "confirmed":
        label = "Room booked" if rental else "Visit confirmed"
        _send(tenant, f"{label} - {room}",
              f"Hi {tenant.username}, your {'room booking' if rental else 'visit'} for '{room}' ({when}) is confirmed. "
              f"Chat with the owner from 'My bookings'.", to_tenant)
        _send(owner, f"{label} - {room}",
              f"Hi {owner.username}, {tenant.username} has a confirmed {'room booking' if rental else 'visit'} "
              f"for '{room}' ({when}).{contact}", to_owner)
    elif event == "cancelled":
        _send(tenant, f"Booking cancelled - {room}",
              f"Hi {tenant.username}, your booking for '{room}' ({when}) was cancelled.", to_tenant)
        _send(owner, f"Booking cancelled - {room}",
              f"Hi {owner.username}, {tenant.username} cancelled their booking ({when}). It's open again.", to_owner)
    elif event == "owner_cancelled":
        _send(tenant, f"Owner cancelled your booking - {room}",
              f"Hi {tenant.username}, the owner had to cancel your booking for '{room}' ({when}). "
              f"Any amount you paid is being refunded in full.", to_tenant)
    elif event == "expired":
        _send(tenant, f"Booking hold expired - {room}",
              f"Hi {tenant.username}, payment wasn't completed in time so your hold on '{room}' ({when}) was released. "
              f"You can book again anytime.", to_tenant)
    elif event == "request_expired":
        _send(tenant, f"Request expired - {room}",
              f"Hi {tenant.username}, the owner didn't respond in time to your request for '{room}' ({when}).", to_tenant)
        _send(owner, f"Request expired - {room}",
              f"Hi {owner.username}, a room request from {tenant.username} expired without a response.", to_owner)


@shared_task
def expire_pending_bookings():
    from .services import expire_stale_pending

    return expire_stale_pending()
