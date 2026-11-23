import datetime
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.utils import timezone
from django.db.models import Avg, Count, F, Q
from django.contrib.auth import get_user_model
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.decorators import phone_verified_required
from bookings.models import Booking
from .forms import BulkSlotForm, ReportForm, ServiceForm, SlotForm
from .alerts import alert_saved_searches
from .filters import SORT_LABELS, active_chips, base_queryset, build_listing, describe
from .models import Amenity, Category, Favorite, Report, SavedSearch, Service, ServiceImage, Slot
from .stats import owner_response_hours
from .realtime import broadcast_slot


def _owner_only(request):
    return request.user.is_authenticated and request.user.is_provider


RECENT_LIMIT = 8


def _recent_rooms(request, exclude=None):
    ids = [i for i in request.session.get("recent", []) if i != exclude]
    if not ids:
        return []
    rooms = {s.pk: s for s in base_queryset(Service.objects.filter(pk__in=ids, is_active=True))}
    return [rooms[i] for i in ids if i in rooms]


def home(request):
    active = Service.objects.filter(is_active=True)
    featured = base_queryset(active).order_by("-created_at")[:6]
    cities = list(active.values_list("city", flat=True).distinct().order_by("city"))
    localities = (active.exclude(location="").values("location", "city")
                  .annotate(n=Count("id")).order_by("-n", "location")[:8])
    stats = {
        "rooms": active.count(),
        "owners": active.values("provider").distinct().count(),
        "cities": len(cities),
        "bookings": Booking.objects.filter(status=Booking.Status.CONFIRMED).count(),
    }
    return render(request, "home.html", {
        "categories": Category.objects.all(), "featured": featured,
        "preferences": Service.TenantPreference.choices, "cities": cities,
        "localities": localities, "stats": stats, "recent": _recent_rooms(request)[:4],
    })


def service_list(request):
    g = request.GET
    services, st = build_listing(g)
    page_obj = Paginator(services, 9).get_page(g.get("page"))

    qs = g.copy()
    qs.pop("page", None)

    user_favorite_ids = set()
    saved_this = False
    if request.user.is_authenticated:
        user_favorite_ids = set(Favorite.objects.filter(user=request.user).values_list("service_id", flat=True))
        saved_this = SavedSearch.objects.filter(user=request.user, params=qs.urlencode()).exists()

    map_points = [
        {"id": s.pk, "title": s.title, "price": str(s.price), "location": s.location,
         "lat": float(s.latitude), "lng": float(s.longitude), "url": reverse("services:detail", args=[s.pk])}
        for s in page_obj if s.has_coordinates
    ]
    chips = active_chips(g, st)
    return render(request, "services/list.html", {
        "page_obj": page_obj, "categories": Category.objects.all(),
        "preferences": Service.TenantPreference.choices, "sort_labels": SORT_LABELS,
        "cities": list(Service.objects.filter(is_active=True).values_list("city", flat=True).distinct().order_by("city")),
        "amenities": Amenity.objects.all(), "st": st,
        "query": st["query"], "category_id": st["category_id"], "locality": st["locality"], "pref": st["pref"],
        "min_price": st["min_price"], "max_price": st["max_price"], "furnished": st["furnished"],
        "verified": st["verified"], "sort": st["sort"], "gender": st["gender"],
        "available_only": st["available_only"], "selected_amenities": st["selected_amenities"],
        "querystring": qs.urlencode(), "chips": chips, "active_filters": len(chips),
        "user_favorite_ids": user_favorite_ids, "map_points": map_points,
        "result_count": page_obj.paginator.count, "saved_this": saved_this,
        "search_label": describe(st), "page_range": page_obj.paginator.get_elided_page_range(page_obj.number, on_each_side=1, on_ends=1),
    })


def _price_insight(service):
    for label, qs in (
        (service.location, Service.objects.filter(is_active=True, location__iexact=service.location)),
        (service.city, Service.objects.filter(is_active=True, city__iexact=service.city)),
    ):
        if not label:
            continue
        others = qs.exclude(pk=service.pk)
        agg = others.aggregate(avg=Avg("price"), n=Count("id"))
        if agg["n"] and agg["n"] >= 2 and agg["avg"]:
            diff = round((float(service.price) - float(agg["avg"])) / float(agg["avg"]) * 100)
            return {"label": label, "avg": round(agg["avg"]), "diff": diff, "abs": abs(diff), "n": agg["n"]}
    return None


def service_detail(request, pk):
    service = get_object_or_404(
        Service.objects.select_related("provider", "category").prefetch_related("images", "amenities"), pk=pk
    )
    if not service.is_active and request.user != service.provider:
        raise Http404

    seen = request.session.get("seen", [])
    if pk not in seen and request.user != service.provider:
        Service.objects.filter(pk=pk).update(view_count=F("view_count") + 1)
        request.session["seen"] = (seen + [pk])[-200:]
    recent = [i for i in request.session.get("recent", []) if i != pk]
    request.session["recent"] = ([pk] + recent)[:RECENT_LIMIT]

    slots = service.open_slots().order_by("date", "start_time")
    my_rental = None
    if request.user.is_authenticated and request.user.is_customer:
        my_rental = service.bookings.filter(
            customer=request.user, kind="RENTAL", status__in=["REQUESTED", "PENDING", "CONFIRMED"],
            stay_end_date__gt=timezone.localdate(),
        ).first()
    month_options = sorted(set(range(service.min_stay_months, 13)) | {18, 24})
    month_options = [m for m in month_options if m >= service.min_stay_months]

    reviews = list(service.reviews.select_related("customer").all())
    breakdown = []
    if reviews:
        total = len(reviews)
        for star in range(5, 0, -1):
            n = sum(1 for r in reviews if r.rating == star)
            breakdown.append({"star": star, "n": n, "pct": round(n / total * 100)})

    is_favorited = has_reported = False
    if request.user.is_authenticated:
        is_favorited = Favorite.objects.filter(user=request.user, service=service).exists()
        has_reported = Report.objects.filter(reporter=request.user, service=service).exists()

    lo, hi = service.price * Decimal("0.7"), service.price * Decimal("1.3")
    similar = list(base_queryset(
        Service.objects.filter(is_active=True, city__iexact=service.city, price__gte=lo, price__lte=hi).exclude(pk=pk)
    ).order_by("-created_at")[:3])

    owner = service.provider
    owner_stats = {
        "since": owner.date_joined, "rooms": owner.services.filter(is_active=True).count(),
        "reply_hours": owner_response_hours(owner),
    }
    images = service.photos
    panoramas = service.panoramas
    first_image = images[0].url if images else (service.image.url if service.image else "")
    return render(request, "services/detail.html", {
        "service": service, "slots": slots, "reviews": reviews, "breakdown": breakdown,
        "is_favorited": is_favorited, "has_reported": has_reported,
        "images": images, "panoramas": panoramas, "report_form": ReportForm(), "is_owner": request.user == service.provider,
        "my_rental": my_rental, "month_options": month_options,
        "today": timezone.localdate(), "max_move_in": timezone.localdate() + datetime.timedelta(days=120),
        "amenity_list": service.amenities.all(), "price_insight": _price_insight(service),
        "similar": similar, "owner_stats": owner_stats, "og_image": first_image,
        "move_in_total": service.price + service.deposit_amount,
    })


def owner_profile(request, username):
    owner = get_object_or_404(get_user_model(), username=username, role="PROVIDER", is_active=True)
    rooms = base_queryset(Service.objects.filter(provider=owner, is_active=True)).order_by("-created_at")
    agg = owner.services.filter(is_active=True).aggregate(avg=Avg("reviews__rating"), n=Count("reviews", distinct=True))
    user_favorite_ids = set()
    if request.user.is_authenticated:
        user_favorite_ids = set(Favorite.objects.filter(user=request.user).values_list("service_id", flat=True))
    return render(request, "services/owner_profile.html", {
        "owner": owner, "rooms": rooms, "avg_rating": round(agg["avg"] or 0, 1), "review_count": agg["n"],
        "reply_hours": owner_response_hours(owner), "user_favorite_ids": user_favorite_ids,
    })


MAX_COMPARE = 3


def _safe_back(request, default):
    nxt = request.POST.get("next", "")
    if nxt.startswith("/") and not nxt.startswith("//"):
        return nxt
    return default


@require_POST
def compare_toggle(request, pk):
    get_object_or_404(Service, pk=pk, is_active=True)
    ids = request.session.get("compare", [])
    if pk in ids:
        ids.remove(pk)
    elif len(ids) >= MAX_COMPARE:
        messages.info(request, f"You can compare up to {MAX_COMPARE} rooms. Remove one first.")
    else:
        ids.append(pk)
    request.session["compare"] = ids
    return redirect(_safe_back(request, reverse("services:list")))


@require_POST
def compare_clear(request):
    request.session["compare"] = []
    return redirect(_safe_back(request, reverse("services:list")))


def compare_view(request):
    ids = request.session.get("compare", [])
    found = {s.pk: s for s in base_queryset(Service.objects.filter(pk__in=ids, is_active=True)).prefetch_related("amenities")}
    rooms = [found[i] for i in ids if i in found]
    all_amenities = sorted({a.name for r in rooms for a in r.amenities.all()})
    return render(request, "services/compare.html", {
        "rooms": rooms, "all_amenities": all_amenities,
        "amenity_sets": {r.pk: {a.name for a in r.amenities.all()} for r in rooms},
        "cheapest": min((r.price for r in rooms), default=None),
    })


@login_required
@require_POST
def save_search(request):
    params = request.POST.get("params", "").strip()[:500]
    if SavedSearch.objects.filter(user=request.user).count() >= 10:
        messages.error(request, "You can keep up to 10 alerts. Delete one first.")
    else:
        from django.http import QueryDict
        _, st = build_listing(QueryDict(params))
        name = describe(st)
        _, created = SavedSearch.objects.get_or_create(user=request.user, params=params, defaults={"name": name})
        messages.success(request, f"Alert saved: {name}. We'll notify you when a new room matches." if created
                         else "You're already getting alerts for this search.")
    return redirect(f"{reverse('services:list')}?{params}" if params else reverse("services:list"))


@login_required
def saved_searches(request):
    return render(request, "services/saved_searches.html", {"searches": request.user.saved_searches.all()})


@login_required
@require_POST
def delete_search(request, pk):
    get_object_or_404(SavedSearch, pk=pk, user=request.user).delete()
    messages.success(request, "Alert removed.")
    return redirect("services:saved_searches")


@login_required
@require_POST
def toggle_favorite(request, pk):
    service = get_object_or_404(Service, pk=pk)
    favorite, created = Favorite.objects.get_or_create(user=request.user, service=service)
    if not created:
        favorite.delete()
        messages.info(request, "Removed from your saved rooms.")
    else:
        messages.success(request, "Saved to your favorites.")
    next_url = request.POST.get("next", "")
    if next_url.startswith("/") and not next_url.startswith("//"):
        return redirect(next_url)
    return redirect("services:detail", pk=service.pk)


@login_required
def my_favorites(request):
    favorites = (
        Favorite.objects.filter(user=request.user)
        .select_related("service", "service__category", "service__provider")
        .prefetch_related("service__images")
    )
    return render(request, "services/favorites.html", {"favorites": favorites})


@login_required
@require_POST
def report_service(request, pk):
    service = get_object_or_404(Service, pk=pk)
    if service.provider_id == request.user.id:
        messages.error(request, "You can't report your own listing.")
        return redirect("services:detail", pk=pk)
    form = ReportForm(request.POST)
    if form.is_valid():
        Report.objects.update_or_create(
            service=service, reporter=request.user,
            defaults={"reason": form.cleaned_data["reason"], "details": form.cleaned_data["details"], "resolved": False},
        )
        messages.success(request, "Thanks - our team will review this listing.")
    else:
        messages.error(request, "Please choose a reason for the report.")
    return redirect("services:detail", pk=pk)


@login_required
def provider_dashboard(request):
    if not request.user.is_provider:
        return redirect("home")
    my_services = list(
        Service.objects.filter(provider=request.user).prefetch_related("images")
        .annotate(
            pending_requests=Count("bookings", filter=Q(bookings__status="REQUESTED"), distinct=True),
            confirmed_visits=Count("bookings", filter=Q(bookings__status="CONFIRMED"), distinct=True),
            total_requests=Count("bookings", filter=Q(bookings__kind="RENTAL"), distinct=True),
            saves=Count("favorited_by", distinct=True),
        ).order_by("-created_at")
    )
    for room in my_services:
        room.conversion = round(room.total_requests / room.view_count * 100) if room.view_count else 0
    totals = {
        "views": sum(r.view_count for r in my_services),
        "saves": sum(r.saves for r in my_services),
        "requests": sum(r.total_requests for r in my_services),
        "awaiting": sum(r.pending_requests for r in my_services),
        "active": sum(1 for r in my_services if r.is_active),
    }
    peak = max([r.view_count for r in my_services] + [1])
    for room in my_services:
        room.view_pct = round(room.view_count / peak * 100)
    return render(request, "services/provider_dashboard.html", {
        "my_services": my_services, "totals": totals, "reply_hours": owner_response_hours(request.user),
    })


@phone_verified_required
def create_service(request):
    if not request.user.is_provider:
        return redirect("home")
    if request.method == "POST":
        form = ServiceForm(request.POST, request.FILES)
        if form.is_valid():
            service = form.save(commit=False)
            service.provider = request.user
            service.save()
            form.save_m2m()
            form.save_images(service)
            alert_saved_searches(service)
            messages.success(request, "Room listed! Now add some visit slots.")
            return redirect("services:manage_slots", pk=service.pk)
    else:
        form = ServiceForm(initial={"whatsapp_number": request.user.phone_number})
    return render(request, "services/create.html", {"form": form, "editing": False})


@login_required
def edit_service(request, pk):
    service = get_object_or_404(Service, pk=pk, provider=request.user)
    if request.method == "POST":
        form = ServiceForm(request.POST, request.FILES, instance=service)
        if form.is_valid():
            form.save()
            delete_ids = [i for i in request.POST.getlist("delete_images") if i.isdigit()]
            if delete_ids:
                for img in service.images.filter(pk__in=delete_ids):
                    img.image.delete(save=False)
                    img.delete()
            form.save_images(service)
            messages.success(request, "Listing updated.")
            return redirect("services:provider_dashboard")
    else:
        form = ServiceForm(instance=service)
    return render(request, "services/create.html", {
        "form": form, "editing": True, "service": service, "existing_images": service.images.all(),
    })


@login_required
@require_POST
def toggle_active(request, pk):
    service = get_object_or_404(Service, pk=pk, provider=request.user)
    service.is_active = not service.is_active
    service.save(update_fields=["is_active"])
    messages.success(request, "Listing is live again." if service.is_active else "Listing paused - tenants can't see it.")
    return redirect("services:provider_dashboard")


@login_required
@require_POST
def delete_service(request, pk):
    service = get_object_or_404(Service, pk=pk, provider=request.user)
    if service.bookings.exclude(status=Booking.Status.CANCELLED).exists():
        messages.error(request, "This room has active bookings, so it can't be deleted. Pause it instead.")
        return redirect("services:provider_dashboard")
    service.delete()
    messages.success(request, "Listing deleted.")
    return redirect("services:provider_dashboard")


@login_required
def manage_slots(request, pk):
    service = get_object_or_404(Service, pk=pk, provider=request.user)
    form, bulk_form = SlotForm(service=service), BulkSlotForm()
    if request.method == "POST":
        if "bulk" in request.POST:
            bulk_form = BulkSlotForm(request.POST)
            if bulk_form.is_valid():
                new = [Slot(service=service, date=d, start_time=s, end_time=e) for d, s, e in bulk_form.iter_slots()]
                before = service.slots.count()
                Slot.objects.bulk_create(new, ignore_conflicts=True)
                added = service.slots.count() - before
                for slot in service.slots.filter(is_booked=False).order_by("-id")[:added]:
                    broadcast_slot(slot)
                messages.success(request, f"Added {added} visit slot{'s' if added != 1 else ''}.")
                return redirect("services:manage_slots", pk=service.pk)
        else:
            form = SlotForm(request.POST, service=service)
            if form.is_valid():
                slot = form.save(commit=False)
                slot.service = service
                try:
                    slot.save()
                except IntegrityError:
                    messages.error(request, "You already have a slot at that time.")
                else:
                    broadcast_slot(slot)
                    return redirect("services:manage_slots", pk=service.pk)
    slots = service.slots.all()
    return render(request, "services/manage_slots.html", {
        "service": service, "form": form, "bulk_form": bulk_form, "slots": slots,
    })


@login_required
@require_POST
def delete_slot(request, pk, slot_id):
    service = get_object_or_404(Service, pk=pk, provider=request.user)
    slot = get_object_or_404(Slot, pk=slot_id, service=service)
    if slot.is_booked:
        messages.error(request, "That slot is booked - it can't be removed.")
    else:
        slot.delete()
        messages.success(request, "Slot removed.")
    return redirect("services:manage_slots", pk=pk)
