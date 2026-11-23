from django.conf import settings
from django.core.management.base import BaseCommand

from accounts.models import OTPCode
from accounts.otp import (OTPError, backend_for, channel_available, deliver, external_start, normalize_phone,
                          uses_verify_service)

CH = OTPCode.Channel


class Command(BaseCommand):
    help = "Show how OTP delivery is configured and optionally send a real test message."

    def add_arguments(self, parser):
        parser.add_argument("--phone")
        parser.add_argument("--via", choices=["whatsapp", "sms"], default="whatsapp")
        parser.add_argument("--email")

    def handle(self, *args, **opts):
        out = self.stdout.write
        out(f"DEBUG={settings.DEBUG}  LOCAL_MODE={settings.LOCAL_MODE}")
        for label, ch in (("WhatsApp", CH.WHATSAPP), ("SMS", CH.PHONE), ("Email", CH.EMAIL)):
            backend = backend_for(ch)
            ok = channel_available(ch)
            note = ""
            if backend == "console":
                note = "  (prints in this terminal - local testing only)"
            elif backend == "twilio_verify":
                have = bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_VERIFY_SERVICE_SID)
                note = "  Twilio Verify credentials found" if have else "  MISSING TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_VERIFY_SERVICE_SID"
            elif backend == "twilio":
                have = bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN)
                note = "  credentials found" if have else "  MISSING TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN"
            elif backend == "meta":
                have = bool(settings.META_WA_TOKEN and settings.META_WA_PHONE_NUMBER_ID and settings.META_WA_TEMPLATE_NAME)
                note = "  credentials found" if have else "  MISSING META_WA_* settings"
            elif backend == "email":
                have = bool(settings.EMAIL_HOST and settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD)
                note = f"  SMTP {settings.EMAIL_HOST}:{settings.EMAIL_PORT}" + ("" if have else "  MISSING EMAIL_HOST / USER / PASSWORD")
            out(f"  {label:<9} backend={backend!r:<10} offered_to_users={ok}{note}")

        if opts["phone"]:
            phone = normalize_phone(opts["phone"])
            if not phone:
                self.stderr.write("That phone number isn't valid.")
                return
            ch = CH.WHATSAPP if opts["via"] == "whatsapp" else CH.PHONE
            self._send(ch, phone)
        if opts["email"]:
            self._send(CH.EMAIL, opts["email"])

    def _send(self, channel, target):
        try:
            if uses_verify_service(channel):
                external_start(channel, target)
            else:
                deliver(channel, target, "123456")
        except OTPError as exc:
            self.stderr.write(self.style.ERROR(f"FAILED ({channel}): {exc}"))
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"FAILED ({channel}): {type(exc).__name__}: {exc}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Sent a test message to {target} via {channel}."))
