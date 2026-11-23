from django.http import QueryDict
from django.urls import reverse

from accounts.notifications import notify
from .filters import build_listing
from .models import SavedSearch, Service


def alert_saved_searches(service):
    count = 0
    for saved in SavedSearch.objects.exclude(user=service.provider).select_related("user")[:1000]:
        params = QueryDict(saved.params)
        qs, _ = build_listing(params, base=Service.objects.filter(pk=service.pk, is_active=True))
        if qs.exists():
            notify(saved.user, f"New room matches '{saved.name}': {service.title} (₹{service.price:.0f}/mo)",
                   reverse("services:detail", args=[service.pk]))
            count += 1
    return count
