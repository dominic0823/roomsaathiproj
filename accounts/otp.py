import hashlib
import hmac
import json
import logging
import math
import re
import secrets
from datetime import timedelta

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import OTPCode

logger = logging.getLogger(__name__)


class OTPError(Exception):
    pass


CH = OTPCode.Channel
PHONE_CHANNELS = (CH.PHONE, CH.WHATSAPP)


def channel_group(channel):
    return PHONE_CHANNELS if channel in PHONE_CHANNELS else (channel,)


def _norm(value):
    return (value or "").strip().lower()


def uses_verify_service(channel):
    return _norm(settings.OTP_PROVIDER) == "twilio_verify" and channel in PHONE_CHANNELS


def backend_for(channel):
    if uses_verify_service(channel):
        return "twilio_verify"
    if channel == CH.WHATSAPP:
        return _norm(settings.OTP_WHATSAPP_BACKEND)
    if channel == CH.PHONE:
        return _norm(settings.OTP_SMS_BACKEND)
    return "console" if "console" in _norm(settings.EMAIL_BACKEND) else "email"


def channel_available(channel):
    if backend_for(channel) != "console":
        return True
    return bool(settings.DEBUG or settings.TESTING)


def _verify_auth():
    sid, token, svc = settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_VERIFY_SERVICE_SID
    if not (sid and token and svc):
        raise ImproperlyConfigured("Twilio Verify settings (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_VERIFY_SERVICE_SID) are missing in .env")
    return sid, token, svc


def external_start(channel, target):
    sid, token, svc = _verify_auth()
    name = "whatsapp" if channel == CH.WHATSAPP else "sms"
    resp = requests.post(f"https://verify.twilio.com/v2/Services/{svc}/Verifications",
                         data={"To": target, "Channel": name}, auth=(sid, token), timeout=15)
    if resp.status_code == 429:
        raise OTPError("Too many codes requested for this number. Please wait a few minutes and try again.")
    if resp.status_code >= 400:
        logger.error("Twilio Verify start failed: %s %s", resp.status_code, resp.text[:300])
        raise OTPError(f"We couldn't send the code by {'WhatsApp' if name == 'whatsapp' else 'text message'}. Please try the other option.")


def external_check(target, code):
    sid, token, svc = _verify_auth()
    resp = requests.post(f"https://verify.twilio.com/v2/Services/{svc}/VerificationCheck",
                         data={"To": target, "Code": code}, auth=(sid, token), timeout=15)
    if resp.status_code == 404:
        return False
    if resp.status_code >= 400:
        logger.error("Twilio Verify check failed: %s %s", resp.status_code, resp.text[:300])
        raise OTPError("We couldn't check that code right now. Please try again in a moment.")
    return resp.json().get("status") == "approved"


def _console_print(text):
    import sys
    sys.stdout.write(text.encode("ascii", "replace").decode("ascii") + "\n")
    sys.stdout.flush()


def _console_allowed():
    return bool(settings.DEBUG or settings.TESTING)


def normalize_phone(value):
    raw = re.sub(r"[\s\-()]", "", value or "")
    if not raw:
        return ""
    if raw.startswith("+"):
        digits = raw[1:]
    elif raw.isdigit() and len(raw) == 10:
        digits = "91" + raw
    elif raw.isdigit() and len(raw) == 11 and raw.startswith("0"):
        digits = "91" + raw[1:]
    elif raw.isdigit() and len(raw) == 12 and raw.startswith("91"):
        digits = raw
    else:
        return None
    if not digits.isdigit():
        return None
    if digits.startswith("91"):
        return "+" + digits if re.fullmatch(r"91[6-9]\d{9}", digits) else None
    return "+" + digits if 8 <= len(digits) <= 14 else None


def mask_target(channel, target):
    if channel == OTPCode.Channel.EMAIL and "@" in target:
        name, domain = target.split("@", 1)
        return f"{name[:2]}{'*' * max(len(name) - 2, 1)}@{domain}"
    return f"{target[:3]}{'*' * max(len(target) - 6, 2)}{target[-3:]}"


def send_sms(phone, text):
    backend = _norm(settings.OTP_SMS_BACKEND)
    if backend == "console":
        if not _console_allowed():
            raise OTPError("Text messages aren't available right now. Please try another option.")
        _console_print(f"\n[OTP SMS -> {phone}] {text}\n")
        return
    if backend == "twilio":
        sid, token = settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN
        if not (sid and token and (settings.TWILIO_FROM_NUMBER or settings.TWILIO_MESSAGING_SERVICE_SID)):
            raise ImproperlyConfigured("Twilio credentials are missing in .env")
        data = {"To": phone, "Body": text}
        if settings.TWILIO_MESSAGING_SERVICE_SID:
            data["MessagingServiceSid"] = settings.TWILIO_MESSAGING_SERVICE_SID
        else:
            data["From"] = settings.TWILIO_FROM_NUMBER
        resp = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
            data=data, auth=(sid, token), timeout=10,
        )
        if resp.status_code >= 400:
            logger.error("Twilio SMS failed: %s %s", resp.status_code, resp.text[:300])
            raise OTPError("We couldn't send the SMS right now. Try the email option or retry shortly.")
        return
    raise ImproperlyConfigured(f"Unknown OTP_SMS_BACKEND '{backend}'")


def send_whatsapp(phone, code, text):
    backend = _norm(settings.OTP_WHATSAPP_BACKEND)
    fail = "We couldn't send the WhatsApp message right now. Try the text message option instead."
    if backend == "console":
        if not _console_allowed():
            raise OTPError("WhatsApp isn't available right now. Please try the text message option.")
        _console_print(f"\n[OTP WhatsApp -> {phone}] {text}\n")
        return

    if backend == "twilio":
        sid, token = settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN
        if not (sid and token and settings.TWILIO_WHATSAPP_FROM):
            raise ImproperlyConfigured("Twilio WhatsApp settings are missing in .env")
        data = {"To": f"whatsapp:{phone}", "From": settings.TWILIO_WHATSAPP_FROM}
        if settings.TWILIO_WHATSAPP_CONTENT_SID:
            data["ContentSid"] = settings.TWILIO_WHATSAPP_CONTENT_SID
            data["ContentVariables"] = json.dumps({"1": code})
        else:
            data["Body"] = text
        resp = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
            data=data, auth=(sid, token), timeout=10,
        )
        if resp.status_code >= 400:
            logger.error("Twilio WhatsApp failed: %s %s", resp.status_code, resp.text[:300])
            raise OTPError(fail)
        return

    if backend == "meta":
        if not (settings.META_WA_TOKEN and settings.META_WA_PHONE_NUMBER_ID and settings.META_WA_TEMPLATE_NAME):
            raise ImproperlyConfigured("Meta WhatsApp settings are missing in .env")
        components = [{"type": "body", "parameters": [{"type": "text", "text": code}]}]
        if settings.META_WA_AUTH_TEMPLATE:
            components.append({"type": "button", "sub_type": "url", "index": "0",
                               "parameters": [{"type": "text", "text": code}]})
        resp = requests.post(
            f"https://graph.facebook.com/{settings.META_WA_GRAPH_VERSION}/{settings.META_WA_PHONE_NUMBER_ID}/messages",
            headers={"Authorization": f"Bearer {settings.META_WA_TOKEN}"},
            json={"messaging_product": "whatsapp", "to": phone.lstrip("+"), "type": "template",
                  "template": {"name": settings.META_WA_TEMPLATE_NAME,
                               "language": {"code": settings.META_WA_TEMPLATE_LANG}, "components": components}},
            timeout=10,
        )
        if resp.status_code >= 400:
            logger.error("Meta WhatsApp failed: %s %s", resp.status_code, resp.text[:300])
            raise OTPError(fail)
        return
    raise ImproperlyConfigured(f"Unknown OTP_WHATSAPP_BACKEND '{backend}'")


def deliver(channel, target, code):
    text = (f"{code} is your RoomSaathi verification code. "
            f"It expires in {settings.OTP_EXPIRY_MINUTES} minutes. Never share it with anyone.")
    if channel == CH.EMAIL:
        if backend_for(CH.EMAIL) == "console" and not _console_allowed():
            raise OTPError("Email isn't available right now. Please try another option.")
        send_mail("Your RoomSaathi verification code", text, settings.DEFAULT_FROM_EMAIL, [target])
    elif channel == CH.WHATSAPP:
        send_whatsapp(target, code, text)
    else:
        send_sms(target, text)


def _hash(user_id, code):
    return hmac.new(settings.SECRET_KEY.encode(), f"{user_id}:{code}".encode(), hashlib.sha256).hexdigest()


def issue_otp(user, channel, target, purpose=OTPCode.Purpose.VERIFY):
    now = timezone.now()
    history = OTPCode.objects.filter(user=user, channel__in=channel_group(channel), purpose=purpose)

    last = history.first()
    if last and (now - last.created_at).total_seconds() < settings.OTP_RESEND_SECONDS:
        wait = math.ceil(settings.OTP_RESEND_SECONDS - (now - last.created_at).total_seconds())
        raise OTPError(f"Please wait {wait} seconds before asking for another code.")
    if history.filter(created_at__gte=now - timedelta(hours=1)).count() >= settings.OTP_MAX_PER_HOUR:
        raise OTPError("Too many codes requested. Please try again in an hour.")

    external = uses_verify_service(channel)
    code = "" if external else f"{secrets.randbelow(10 ** 6):06d}"
    with transaction.atomic():
        history.filter(used_at__isnull=True).update(used_at=now)
        otp = OTPCode.objects.create(
            user=user, channel=channel, purpose=purpose, target=target,
            code_hash="external" if external else _hash(user.id, code),
            expires_at=now + timedelta(minutes=settings.OTP_EXPIRY_MINUTES),
        )
    try:
        if external:
            external_start(channel, target)
        else:
            deliver(channel, target, code)
    except OTPError:
        otp.delete()
        raise
    except Exception as exc:
        logger.exception("OTP delivery failed (%s)", channel)
        otp.delete()
        if settings.DEBUG:
            raise OTPError(f"[Setup problem - visible in DEBUG only] {type(exc).__name__}: {exc}")
        raise OTPError("We couldn't send the code right now. Please try again in a minute.")
    return code


def verify_otp(user, channel, target, code, purpose=OTPCode.Purpose.VERIFY):
    now = timezone.now()
    otp = OTPCode.objects.filter(
        user=user, channel__in=channel_group(channel), purpose=purpose, target=target,
        used_at__isnull=True, expires_at__gt=now,
    ).first()
    if otp is None:
        return False, "That code has expired or was never requested. Please ask for a new one."
    if otp.attempts >= settings.OTP_MAX_ATTEMPTS:
        OTPCode.objects.filter(pk=otp.pk).update(used_at=now)
        return False, "Too many wrong attempts. Please request a new code."

    digits = re.sub(r"\D", "", code or "")
    if otp.code_hash == "external" and len(digits) >= 4:
        try:
            matched = external_check(target, digits)
        except OTPError as exc:
            return False, str(exc)
    else:
        matched = len(digits) == 6 and otp.code_hash != "external" and hmac.compare_digest(otp.code_hash, _hash(user.id, digits))
    if not matched:
        OTPCode.objects.filter(pk=otp.pk).update(attempts=F("attempts") + 1)
        left = settings.OTP_MAX_ATTEMPTS - (otp.attempts + 1)
        if left <= 0:
            OTPCode.objects.filter(pk=otp.pk).update(used_at=now)
            return False, "Incorrect code. Please request a new one."
        return False, f"Incorrect code. {left} attempt{'s' if left != 1 else ''} left."

    OTPCode.objects.filter(pk=otp.pk).update(used_at=now)
    return True, ""


def active_otp(user, channel, target, purpose=OTPCode.Purpose.VERIFY):
    return OTPCode.objects.filter(
        user=user, channel__in=channel_group(channel), purpose=purpose, target=target,
        used_at__isnull=True, expires_at__gt=timezone.now(),
    ).first()


def resend_wait_seconds(user, channel, purpose=OTPCode.Purpose.VERIFY):
    last = OTPCode.objects.filter(user=user, channel__in=channel_group(channel), purpose=purpose).first()
    if not last:
        return 0
    return max(0, math.ceil(settings.OTP_RESEND_SECONDS - (timezone.now() - last.created_at).total_seconds()))
