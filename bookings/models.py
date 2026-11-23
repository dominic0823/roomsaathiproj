from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from services.models import Slot, Service


class Booking(models.Model):

    class Kind(models.TextChoices):
        VISIT = "VISIT", "Visit"
        RENTAL = "RENTAL", "Room booking"

    class Status(models.TextChoices):
        REQUESTED = "REQUESTED", "Awaiting owner approval"
        PENDING = "PENDING", "Pending payment"
        CONFIRMED = "CONFIRMED", "Confirmed"
        DECLINED = "DECLINED", "Declined by owner"
        CANCELLED = "CANCELLED", "Cancelled"

    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.VISIT)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings")
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="bookings")
    slot = models.ForeignKey(Slot, on_delete=models.CASCADE, related_name="bookings", null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    total_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Amount payable online (token / advance)")
    created_at = models.DateTimeField(auto_now_add=True)

    move_in_date = models.DateField(null=True, blank=True)
    stay_months = models.PositiveSmallIntegerField(null=True, blank=True)
    stay_end_date = models.DateField(null=True, blank=True)
    tenant_note = models.CharField(max_length=500, blank=True)
    owner_note = models.CharField(max_length=500, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    monthly_rent = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["slot"],
                condition=Q(slot__isnull=False) & ~Q(status__in=["CANCELLED", "DECLINED"]),
                name="unique_active_booking_per_slot",
            ),
            models.CheckConstraint(
                check=Q(kind="RENTAL") | Q(slot__isnull=False),
                name="visit_booking_needs_slot",
            ),
        ]

    def __str__(self):
        return f"Booking #{self.id} - {self.service.title}"

    @property
    def is_rental(self):
        return self.kind == self.Kind.RENTAL

    @property
    def when_label(self):
        if self.is_rental:
            months = f"{self.stay_months} month{'s' if self.stay_months != 1 else ''}"
            return f"Move in {self.move_in_date:%d %b %Y} · {months}"
        return self.slot.label if self.slot_id else ""

    @property
    def expires_at(self):
        if self.is_rental:
            if self.status == self.Status.REQUESTED:
                return self.created_at + timedelta(hours=settings.RENTAL_REQUEST_HOURS)
            return (self.approved_at or self.created_at) + timedelta(hours=settings.RENTAL_PAYMENT_HOURS)
        return self.created_at + timedelta(minutes=settings.PENDING_BOOKING_MINUTES)

    @property
    def is_expired(self):
        return self.status in (self.Status.PENDING, self.Status.REQUESTED) and timezone.now() >= self.expires_at

    @property
    def chat_enabled(self):
        if self.status == self.Status.CONFIRMED:
            return True
        return self.is_rental and self.status in (self.Status.REQUESTED, self.Status.PENDING)

    @property
    def can_review(self):
        if self.status != self.Status.CONFIRMED:
            return False
        if self.is_rental:
            return self.move_in_date <= timezone.localdate()
        return self.slot.is_past

    @property
    def refund_eligible(self):
        if self.is_rental:
            days = (self.move_in_date - timezone.localdate()).days
            return days >= settings.RENTAL_REFUND_DAYS_BEFORE_MOVE_IN
        return True
