import datetime
import re
from decimal import Decimal
from urllib.parse import quote

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Count, Q
from django.utils import timezone


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    icon = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class Amenity(models.Model):
    name = models.CharField(max_length=60, unique=True)
    icon = models.CharField(max_length=8, blank=True)

    class Meta:
        verbose_name_plural = "Amenities"
        ordering = ["name"]

    def __str__(self):
        return f"{self.icon} {self.name}".strip()


class Service(models.Model):

    class Gender(models.TextChoices):
        ANY = "ANY", "Anyone"
        MALE = "MALE", "Boys / Men only"
        FEMALE = "FEMALE", "Girls / Women only"

    class TenantPreference(models.TextChoices):
        ANYONE = "ANYONE", "Anyone"
        STUDENT = "STUDENT", "Students"
        FAMILY = "FAMILY", "Family"
        DEFENCE = "DEFENCE", "Defence / Army personnel"
        WORKING_PROFESSIONAL = "WORKING_PROFESSIONAL", "Working professionals"

    provider = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="services"
    )
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="services")
    title = models.CharField(max_length=150)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Monthly rent (₹)")
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Refundable security deposit (₹)")
    booking_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=500,
        validators=[MinValueValidator(Decimal('0'))],
        help_text="Token amount a tenant pays to reserve a visit (₹). Use 0 for free visits.",
    )
    advance_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=2000,
        validators=[MinValueValidator(Decimal('0'))],
        help_text="Advance a tenant pays online to reserve the room (adjusted against first rent). 0 = no advance.",
    )
    total_beds = models.PositiveIntegerField(
        default=1, validators=[MinValueValidator(1)],
        help_text="How many tenants can stay (1 for a private room, more for a PG/shared room)",
    )
    gender_allowed = models.CharField(max_length=6, choices=Gender.choices, default=Gender.ANY)
    amenities = models.ManyToManyField(Amenity, blank=True, related_name="services")
    min_stay_months = models.PositiveIntegerField(default=1, help_text="Minimum stay required, in months")
    is_furnished = models.BooleanField(default=False)
    tenant_preference = models.CharField(
        max_length=25, choices=TenantPreference.choices, default=TenantPreference.ANYONE
    )
    city = models.CharField(max_length=60, default="Delhi", db_index=True)
    location = models.CharField(max_length=150, blank=True, help_text="Locality / area")
    view_count = models.PositiveIntegerField(default=0, editable=False)
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        validators=[MinValueValidator(Decimal('-90')), MaxValueValidator(Decimal('90'))],
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        validators=[MinValueValidator(Decimal('-180')), MaxValueValidator(Decimal('180'))],
    )
    whatsapp_number = models.CharField(
        max_length=15, blank=True,
        help_text="Optional. If you add it, it's shown publicly as a 'Chat on WhatsApp' button.",
    )
    image = models.ImageField(upload_to="services/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse("services:detail", args=[self.pk])

    def open_slots(self):
        now = timezone.localtime()
        return self.slots.filter(is_booked=False).filter(
            Q(date__gt=now.date()) | Q(date=now.date(), start_time__gt=now.time())
        )

    @property
    def available_slot_count(self):
        return self.open_slots().count()

    RENTAL_HOLDING = ("PENDING", "CONFIRMED")

    @property
    def occupied_beds(self):
        annotated = getattr(self, "occupied", None)
        if annotated is not None:
            return annotated
        return self.bookings.filter(
            kind="RENTAL", status__in=self.RENTAL_HOLDING, stay_end_date__gt=timezone.localdate()
        ).count()

    @property
    def beds_left(self):
        return max(0, self.total_beds - self.occupied_beds)

    @property
    def is_full(self):
        return self.beds_left <= 0

    def beds_left_between(self, start, end):
        taken = self.bookings.filter(
            kind="RENTAL", status__in=self.RENTAL_HOLDING, move_in_date__lt=end, stay_end_date__gt=start
        ).count()
        return max(0, self.total_beds - taken)

    @property
    def rating_summary(self):
        agg = self.reviews.aggregate(avg=Avg("rating"), count=Count("id"))
        return {"avg": round(agg["avg"] or 0, 1), "count": agg["count"] or 0}

    @property
    def favorite_count(self):
        return self.favorited_by.count()

    @property
    def full_stars_range(self):
        return range(round(self.rating_summary["avg"]))

    @property
    def empty_stars_range(self):
        return range(5 - round(self.rating_summary["avg"]))

    @property
    def photos(self):
        return [i for i in self.images.all() if not i.is_360 and i.url]

    @property
    def panoramas(self):
        return [i for i in self.images.all() if i.is_360 and i.url]

    @property
    def has_360(self):
        return bool(self.panoramas)

    @property
    def cover_url(self):
        photos = self.photos
        if photos:
            return photos[0].url
        if self.image:
            return self.image.url
        return ""

    @property
    def has_coordinates(self):
        return self.latitude is not None and self.longitude is not None

    @property
    def whatsapp_link(self):
        digits = re.sub(r"\D", "", self.whatsapp_number or "")
        if len(digits) == 10:
            digits = "91" + digits
        if len(digits) < 11:
            return ""
        text = quote(f"Hi, I'm interested in your room '{self.title}' on RoomSaathi.")
        return f"https://wa.me/{digits}?text={text}"


class ServiceImage(models.Model):
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="services/", blank=True, null=True)
    image_url = models.URLField(max_length=600, blank=True)
    is_360 = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    @property
    def url(self):
        return self.image.url if self.image else self.image_url

    def __str__(self):
        return f"Image {self.pk} of {self.service_id}"


class Slot(models.Model):
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="slots")
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_booked = models.BooleanField(default=False)

    class Meta:
        ordering = ["date", "start_time"]
        unique_together = ("service", "date", "start_time")

    def __str__(self):
        return f"{self.service.title} | {self.date} {self.start_time}"

    @property
    def starts_at(self):
        return timezone.make_aware(datetime.datetime.combine(self.date, self.start_time))

    @property
    def is_past(self):
        return self.starts_at <= timezone.now()

    @property
    def label(self):
        return f"{self.date:%a, %d %b} · {self.start_time:%H:%M} - {self.end_time:%H:%M}"

    @property
    def sort_key(self):
        return f"{self.date.isoformat()}T{self.start_time.strftime('%H:%M')}"


class Review(models.Model):
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="reviews")
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews"
    )
    booking = models.OneToOneField(
        "bookings.Booking", on_delete=models.CASCADE, related_name="review"
    )
    rating = models.PositiveSmallIntegerField(
        default=5, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.rating}\u2605 by {self.customer.username} on {self.service.title}"

    @property
    def stars_range(self):
        return range(self.rating)

    @property
    def empty_stars_range(self):
        return range(5 - self.rating)


class Favorite(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorites"
    )
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="favorited_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "service")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} \u2764 {self.service.title}"


class Report(models.Model):

    class Reason(models.TextChoices):
        SCAM = "SCAM", "Looks like a scam / asks for money outside the app"
        WRONG_INFO = "WRONG_INFO", "Wrong price, photos or details"
        UNAVAILABLE = "UNAVAILABLE", "Room is no longer available"
        INAPPROPRIATE = "INAPPROPRIATE", "Inappropriate content"
        OTHER = "OTHER", "Something else"

    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="reports")
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reports")
    reason = models.CharField(max_length=20, choices=Reason.choices)
    details = models.TextField(blank=True)
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("service", "reporter")
        ordering = ["resolved", "-created_at"]

    def __str__(self):
        return f"Report on {self.service.title} ({self.get_reason_display()})"


class SavedSearch(models.Model):

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_searches")
    name = models.CharField(max_length=120)
    params = models.CharField(max_length=500, help_text="URL query string of the filters")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("user", "params")

    def __str__(self):
        return f"{self.user_id}: {self.name}"
