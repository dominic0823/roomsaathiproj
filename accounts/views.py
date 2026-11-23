from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.urls import reverse
from django.views import View
from django.views.decorators.http import require_POST

from .decorators import safe_next
from .forms import ProfileForm, RegisterForm, VerificationRequestForm
from .models import OTPCode, User
from .otp import (OTPError, active_otp, backend_for, channel_available, issue_otp, mask_target,
                  normalize_phone, resend_wait_seconds, verify_otp)

CH = OTPCode.Channel


class RegisterView(View):
    template_name = "accounts/register.html"

    def get(self, request):
        role = request.GET.get("role")
        initial = {"role": role} if role in User.Role.values else {}
        return render(request, self.template_name, {"form": RegisterForm(initial=initial)})

    def post(self, request):
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Account created! Verify your mobile number to start booking or listing rooms.")
            return redirect("accounts:verify", channel="phone")
        return render(request, self.template_name, {"form": form})


class MarketplaceLoginView(LoginView):
    template_name = "accounts/login.html"


def logout_view(request):
    logout(request)
    return redirect("home")


def _echo(request, code, channel):
    request.session.pop("demo_otp", None)
    if code and settings.OTP_DEV_ECHO and backend_for(channel) == "console":
        request.session["demo_otp"] = code


def _send_channel(request):
    return CH.WHATSAPP if request.POST.get("via") == "whatsapp" else CH.PHONE


def _via_label(channel):
    return {CH.WHATSAPP: "WhatsApp", CH.PHONE: "text message", CH.EMAIL: "email"}[channel]


def _otp_context(user, ch, target, extra=None):
    active = active_otp(user, ch, target)
    ctx = {
        "has_active": active is not None,
        "sent_via": _via_label(active.channel) if active else "",
        "sent_via_code": active.channel if active else "",
        "wait": resend_wait_seconds(user, ch),
        "expires_in": max(0, int((active.expires_at - timezone.now()).total_seconds())) if active else 0,
        "expiry": settings.OTP_EXPIRY_MINUTES,
        "whatsapp_ok": channel_available(CH.WHATSAPP),
        "sms_ok": channel_available(CH.PHONE),
        "email_ok": channel_available(CH.EMAIL),
    }
    ctx.update(extra or {})
    return ctx


@login_required
def verify_contact(request, channel):
    if channel not in ("phone", "email"):
        raise Http404
    user = request.user
    is_phone = channel == "phone"
    ch = CH.PHONE if is_phone else CH.EMAIL
    target = user.phone_number if is_phone else user.email
    already = user.phone_verified if is_phone else user.email_verified
    nxt = safe_next(request, request.POST.get("next") or request.GET.get("next"))
    here = reverse("accounts:verify", args=[channel]) + (f"?{urlencode({'next': nxt})}" if nxt else "")

    if already:
        messages.success(request, f"Your {channel} is already verified.")
        return redirect(nxt or "accounts:profile")
    if not target:
        messages.error(request, f"Add your {channel} on the profile page first.")
        return redirect("accounts:profile")
    if is_phone and User.objects.filter(phone_number=target, phone_verified=True).exclude(pk=user.pk).exists():
        messages.error(request, "This number is already verified on another account. Use a different number.")
        return redirect("accounts:profile")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "send":
            send_ch = _send_channel(request) if is_phone else CH.EMAIL
            try:
                code = issue_otp(user, send_ch, target)
            except OTPError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f"Done! We sent a 6-digit code to {mask_target(ch, target)} by {_via_label(send_ch)}.")
                _echo(request, code, send_ch)
            return redirect(here)
        if action == "verify":
            ok, msg = verify_otp(user, ch, target, request.POST.get("code"))
            if ok:
                if is_phone:
                    user.phone_verified = True
                    user.save(update_fields=["phone_verified"])
                    request.session.pop("demo_otp", None)
                else:
                    user.email_verified = True
                    user.save(update_fields=["email_verified"])
                    request.session.pop("demo_otp", None)
                messages.success(request, f"{channel.capitalize()} verified. Thank you!")
                return redirect(nxt or "accounts:profile")
            messages.error(request, msg)
            return redirect(here)

    return render(request, "accounts/verify_otp.html", _otp_context(user, ch, target, {
        "channel": channel, "masked": mask_target(ch, target), "next": nxt,
        "demo_otp": request.session.get("demo_otp"),
    }))


def login_otp(request):
    if request.user.is_authenticated:
        return redirect("home")
    nxt = safe_next(request, request.POST.get("next") or request.GET.get("next"))
    session_phone = request.session.get("otp_login_phone")
    context = {"next": nxt, "phone": session_phone, "step": "code" if session_phone else "phone",
               "whatsapp_ok": channel_available(CH.WHATSAPP), "sms_ok": channel_available(CH.PHONE),
               "wait": 0, "expiry": settings.OTP_EXPIRY_MINUTES, "masked": mask_target(CH.PHONE, session_phone) if session_phone else ""}
    if session_phone:
        context["demo_otp"] = request.session.get("demo_otp")
        pending = User.objects.filter(phone_number=session_phone, phone_verified=True, is_active=True).first()
        if pending:
            context["wait"] = resend_wait_seconds(pending, CH.PHONE, OTPCode.Purpose.LOGIN)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "change":
            request.session.pop("otp_login_phone", None)
            return redirect(request.get_full_path())
        if action == "send":
            phone = normalize_phone(request.POST.get("phone"))
            if not phone:
                messages.error(request, "Enter a valid mobile number.")
                return redirect(request.get_full_path())
            user = User.objects.filter(phone_number=phone, phone_verified=True, is_active=True).first()
            if user:
                send_ch = _send_channel(request)
                try:
                    _echo(request, issue_otp(user, send_ch, phone, OTPCode.Purpose.LOGIN), send_ch)
                except OTPError:
                    pass
            request.session["otp_login_phone"] = phone
            messages.success(request, "If this number is registered, a 6-digit code is on its way - check WhatsApp or your messages.")
            return redirect(request.get_full_path())
        if action == "verify" and session_phone:
            user = User.objects.filter(phone_number=session_phone, phone_verified=True, is_active=True).first()
            ok, msg = (False, "Incorrect or expired code.")
            if user:
                ok, msg = verify_otp(user, CH.PHONE, session_phone, request.POST.get("code"), OTPCode.Purpose.LOGIN)
            if ok:
                request.session.pop("otp_login_phone", None)
                request.session.pop("demo_otp", None)
                login(request, user, backend="django.contrib.auth.backends.ModelBackend")
                return redirect(nxt or "home")
            messages.error(request, msg)
            return redirect(request.get_full_path())
    return render(request, "accounts/login_otp.html", context)


@login_required
def profile(request):
    user = request.user
    if request.method == "POST":
        old_phone, old_email = user.phone_number, user.email
        form = ProfileForm(request.POST, instance=user)
        if form.is_valid():
            obj = form.save(commit=False)
            if obj.phone_number != old_phone:
                obj.phone_verified = False
            if obj.email != old_email:
                obj.email_verified = False
            obj.save()
            messages.success(request, "Profile updated.")
            return redirect("accounts:profile")
    else:
        form = ProfileForm(instance=user)
    steps = [("Add your name", bool(user.first_name)), ("Verify your mobile number", user.phone_verified),
             ("Verify your email", user.email_verified)]
    if user.is_provider:
        steps.append(("Get the Verified owner badge", user.is_verified))
    done = sum(1 for _, ok in steps if ok)
    return render(request, "accounts/profile.html", {
        "form": form, "checklist": steps, "progress": round(done / len(steps) * 100),
    })


@login_required
def verification(request):
    if not request.user.is_provider:
        return redirect("home")
    user = request.user
    if request.method == "POST" and not user.is_verified:
        if not user.phone_verified:
            messages.info(request, "Verify your phone number first.")
            return redirect("accounts:verify", channel="phone")
        form = VerificationRequestForm(request.POST, instance=user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.verification_requested = True
            obj.save()
            messages.success(request, "Request sent. Our team will contact you on your phone number.")
            return redirect("accounts:verification")
    else:
        form = VerificationRequestForm(instance=user)
    return render(request, "accounts/verification.html", {"form": form})


@login_required
def notifications(request):
    items = list(request.user.notifications.all()[:50])
    response = render(request, "accounts/notifications.html", {"items": items})
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return response


@login_required
@require_POST
def clear_notifications(request):
    request.user.notifications.all().delete()
    return redirect("accounts:notifications")
