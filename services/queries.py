from django.db.models import Count, IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone


def with_occupancy(qs):
    from bookings.models import Booking

    sub = (
        Booking.objects.filter(
            service=OuterRef("pk"), kind="RENTAL", status__in=["PENDING", "CONFIRMED"],
            stay_end_date__gt=timezone.localdate(),
        )
        .order_by().values("service").annotate(c=Count("pk")).values("c")
    )
    return qs.annotate(occupied=Coalesce(Subquery(sub, output_field=IntegerField()), Value(0)))
