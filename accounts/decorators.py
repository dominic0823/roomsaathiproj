from functools import wraps
from urllib.parse import urlencode, urlparse

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme


def safe_next(request, candidate):
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        parsed = urlparse(candidate)
        return parsed._replace(scheme="", netloc="").geturl() or "/"
    return ""


def phone_verified_required(view):

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if settings.REQUIRE_PHONE_VERIFICATION and not request.user.phone_verified:
            messages.info(request, "Please verify your phone number first - it takes a minute and keeps everyone safe.")
            candidate = request.META.get("HTTP_REFERER") if request.method == "POST" else request.get_full_path()
            nxt = safe_next(request, candidate)
            url = reverse("accounts:verify", args=["phone"])
            return redirect(f"{url}?{urlencode({'next': nxt})}" if nxt else url)
        return view(request, *args, **kwargs)

    return wrapper
