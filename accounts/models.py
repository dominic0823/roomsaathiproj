from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        CUSTOMER = "CUSTOMER", "Kirayedaar / Tenant (looking for a room)"
        PROVIDER = "PROVIDER", "Makan Maalik / Owner (listing a room)"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)
    phone_number = models.CharField(max_length=15, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)

    phone_verified = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)

    is_verified = models.BooleanField(
        default=False, help_text="Shown as a 'Verified owner' badge on listings."
    )
    verification_requested = models.BooleanField(default=False)
    verification_note = models.TextField(
        blank=True, help_text="Owner's note for the verification team."
    )

    @property
    def is_provider(self):
        return self.role == self.Role.PROVIDER

    @property
    def is_customer(self):
        return self.role == self.Role.CUSTOMER

    @property
    def is_owner(self):
        return self.is_provider

    @property
    def is_tenant(self):
        return self.is_customer


class OTPCode(models.Model):

    class Channel(models.TextChoices):
        PHONE = "PHONE", "Phone (SMS)"
        WHATSAPP = "WHATSAPP", "WhatsApp"
        EMAIL = "EMAIL", "Email"

    class Purpose(models.TextChoices):
        VERIFY = "VERIFY", "Verify contact"
        LOGIN = "LOGIN", "Log in"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="otp_codes")
    channel = models.CharField(max_length=10, choices=Channel.choices)
    purpose = models.CharField(max_length=10, choices=Purpose.choices, default=Purpose.VERIFY)
    target = models.CharField(max_length=254)
    code_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"OTP {self.channel}/{self.purpose} for {self.user_id}"


class Notification(models.Model):

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    message = models.CharField(max_length=255)
    url = models.CharField(max_length=200, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user_id}: {self.message[:40]}"
