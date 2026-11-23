from django.db.models import Avg, Count, F, ExpressionWrapper, DurationField

from bookings.models import Booking


def owner_response_hours(owner):
    qs = Booking.objects.filter(
        service__provider=owner, kind="RENTAL", approved_at__isnull=False
    ).annotate(delta=ExpressionWrapper(F("approved_at") - F("created_at"), output_field=DurationField()))
    agg = qs.aggregate(avg=Avg("delta"), n=Count("id"))
    if not agg["n"] or agg["n"] < 2 or agg["avg"] is None:
        return None
    return max(1, round(agg["avg"].total_seconds() / 3600))
