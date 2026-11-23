from django.conf import settings


def notifications(request):
    user = getattr(request, "user", None)
    count = user.notifications.filter(is_read=False).count() if user is not None and user.is_authenticated else 0
    return {
        "unread_notifications": count,
        "phone_required": settings.REQUIRE_PHONE_VERIFICATION,
        "demo_mode": settings.DEMO_MODE,
        "payment_mode": settings.PAYMENT_MODE,
    }
