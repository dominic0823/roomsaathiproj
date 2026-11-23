from decimal import Decimal, InvalidOperation

from django.db.models import Avg, Count, F, Q

from .models import Service
from .queries import with_occupancy

SORTS = {
    "newest": ("-created_at",),
    "price_low": ("price",),
    "price_high": ("-price",),
    "rating": (F("avg_rating").desc(nulls_last=True), "-created_at"),
    "popular": ("-view_count", "-created_at"),
}
SORT_LABELS = [("newest", "Newest first"), ("popular", "Most viewed"), ("rating", "Top rated"),
               ("price_low", "Price: low to high"), ("price_high", "Price: high to low")]


def _decimal(value):
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return None


def base_queryset(base=None):
    qs = base if base is not None else Service.objects.filter(is_active=True)
    return with_occupancy(
        qs.select_related("category", "provider").prefetch_related("images")
        .annotate(avg_rating=Avg("reviews__rating"), review_count=Count("reviews", distinct=True))
    )


def build_listing(params, base=None):
    g = params
    qs = base_queryset(base)

    st = {
        "query": g.get("q", "").strip(),
        "city": g.get("city", "").strip(),
        "category_id": g.get("category", ""),
        "locality": g.get("locality", "").strip(),
        "pref": g.get("pref", ""),
        "gender": g.get("gender", ""),
        "min_price": g.get("min_price", ""),
        "max_price": g.get("max_price", ""),
        "furnished": g.get("furnished") == "1",
        "verified": g.get("verified") == "1",
        "available_only": g.get("available") == "1",
        "selected_amenities": [a for a in g.getlist("amenity") if a.isdigit()],
        "sort": g.get("sort", "newest") if g.get("sort", "newest") in SORTS else "newest",
    }
    lo, hi = _decimal(st["min_price"]), _decimal(st["max_price"])

    if st["query"]:
        qs = qs.filter(Q(title__icontains=st["query"]) | Q(description__icontains=st["query"])
                       | Q(location__icontains=st["query"]) | Q(city__icontains=st["query"]))
    if st["city"]:
        qs = qs.filter(city__iexact=st["city"])
    if st["category_id"].isdigit():
        qs = qs.filter(category_id=st["category_id"])
    if st["locality"]:
        qs = qs.filter(location__icontains=st["locality"])
    if st["pref"] in Service.TenantPreference.values:
        qs = qs.filter(Q(tenant_preference=st["pref"]) | Q(tenant_preference="ANYONE"))
    if st["gender"] in ("MALE", "FEMALE"):
        qs = qs.filter(Q(gender_allowed=st["gender"]) | Q(gender_allowed="ANY"))
    for amenity_id in st["selected_amenities"]:
        qs = qs.filter(amenities=amenity_id)
    if lo is not None:
        qs = qs.filter(price__gte=lo)
    if hi is not None:
        qs = qs.filter(price__lte=hi)
    if st["available_only"]:
        qs = qs.filter(total_beds__gt=F("occupied"))
    if st["furnished"]:
        qs = qs.filter(is_furnished=True)
    if st["verified"]:
        qs = qs.filter(provider__is_verified=True)

    st["valid_min"], st["valid_max"] = lo, hi
    return qs.order_by(*SORTS[st["sort"]]), st


def describe(st):
    bits = []
    if st["city"]:
        bits.append(st["city"])
    if st["locality"]:
        bits.append(st["locality"])
    if st["query"]:
        bits.append(f'"{st["query"]}"')
    if st["pref"] in Service.TenantPreference.values and st["pref"] != "ANYONE":
        bits.append(dict(Service.TenantPreference.choices)[st["pref"]])
    if st["gender"] in ("MALE", "FEMALE"):
        bits.append("Boys" if st["gender"] == "MALE" else "Girls")
    if st["valid_max"] is not None and st["valid_min"] is None:
        bits.append(f"under ₹{int(st['valid_max']):,}")
    elif st["valid_min"] is not None or st["valid_max"] is not None:
        lo = f"₹{int(st['valid_min']):,}" if st["valid_min"] is not None else "₹0"
        hi = f"₹{int(st['valid_max']):,}" if st["valid_max"] is not None else "any"
        bits.append(f"{lo}–{hi}")
    if st["furnished"]:
        bits.append("Furnished")
    if st["available_only"]:
        bits.append("Beds free")
    if st["verified"]:
        bits.append("Verified owners")
    return " · ".join(bits)[:120] or "All rooms"


def active_chips(request_get, st):
    from urllib.parse import urlencode

    chips = []

    def without(*keys):
        q = request_get.copy()
        q.pop("page", None)
        for k in keys:
            q.pop(k, None)
        enc = q.urlencode()
        return f"?{enc}" if enc else "?"

    pref_labels = dict(Service.TenantPreference.choices)
    if st["city"]:
        chips.append((st["city"], without("city")))
    if st["locality"]:
        chips.append((st["locality"], without("locality")))
    if st["query"]:
        chips.append((f'"{st["query"]}"', without("q")))
    if st["pref"] in pref_labels and st["pref"] != "ANYONE":
        chips.append((pref_labels[st["pref"]], without("pref")))
    if st["gender"] in ("MALE", "FEMALE"):
        chips.append(("Boys" if st["gender"] == "MALE" else "Girls", without("gender")))
    if st["valid_min"] is not None:
        chips.append((f"Min ₹{int(st['valid_min']):,}", without("min_price")))
    if st["valid_max"] is not None:
        chips.append((f"Max ₹{int(st['valid_max']):,}", without("max_price")))
    if st["furnished"]:
        chips.append(("Furnished", without("furnished")))
    if st["available_only"]:
        chips.append(("Beds free", without("available")))
    if st["verified"]:
        chips.append(("Verified owners", without("verified")))
    if st["selected_amenities"]:
        chips.append((f"{len(st['selected_amenities'])} amenities", without("amenity")))
    return chips
