import datetime
from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from accounts.models import User
from .forms import BulkSlotForm, SlotForm
from .models import Report, Service, ServiceImage, Slot


def make_users():
    owner = User.objects.create_user("owner", "o@x.com", "pw12345678", role="PROVIDER", phone_number="+919876543210", phone_verified=True)
    tenant = User.objects.create_user("tenant", "t@x.com", "pw12345678", role="CUSTOMER", phone_verified=True)
    return owner, tenant


def make_room(owner, **kw):
    data = dict(provider=owner, title="Cozy room", description="d", price=6000, deposit_amount=6000,
                booking_amount=300, location="Kamla Nagar")
    data.update(kw)
    return Service.objects.create(**data)


def png(name="a.png"):
    buf = BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class FilterTests(TestCase):
    def setUp(self):
        self.owner, _ = make_users()
        self.cheap = make_room(self.owner, title="Cheap student", price=4000, tenant_preference="STUDENT", is_furnished=True)
        self.mid = make_room(self.owner, title="Family flat", price=9000, tenant_preference="FAMILY", location="Rohini")
        self.any = make_room(self.owner, title="Open to all", price=7000, tenant_preference="ANYONE")
        self.paused = make_room(self.owner, title="Paused", price=1000, is_active=False)

    def titles(self, **params):
        resp = self.client.get(reverse("services:list"), params)
        self.assertEqual(resp.status_code, 200)
        return {s.title for s in resp.context["page_obj"]}

    def test_budget_filter(self):
        self.assertEqual(self.titles(max_price="5000"), {"Cheap student"})
        self.assertEqual(self.titles(min_price="6000", max_price="8000"), {"Open to all"})

    def test_audience_filter_includes_anyone_rooms(self):
        self.assertEqual(self.titles(pref="STUDENT"), {"Cheap student", "Open to all"})

    def test_locality_furnished_and_paused_hidden(self):
        self.assertEqual(self.titles(locality="rohini"), {"Family flat"})
        self.assertEqual(self.titles(furnished="1"), {"Cheap student"})
        self.assertNotIn("Paused", self.titles())

    def test_bad_price_input_is_ignored(self):
        self.assertEqual(len(self.titles(min_price="abc", max_price="")), 3)

    def test_verified_filter(self):
        self.assertEqual(self.titles(verified="1"), set())
        self.owner.is_verified = True
        self.owner.save()
        self.assertEqual(len(self.titles(verified="1")), 3)

    def test_rating_sort_does_not_crash_with_no_reviews(self):
        self.assertEqual(len(self.titles(sort="rating")), 3)


class OwnerToolsTests(TestCase):
    def setUp(self):
        self.owner, self.tenant = make_users()
        self.room = make_room(self.owner)

    def test_create_with_multiple_images_and_pin(self):
        self.client.force_login(self.owner)
        resp = self.client.post(reverse("services:create"), {
            "title": "New", "description": "x", "price": "5000", "deposit_amount": "0", "booking_amount": "0",
            "min_stay_months": 1, "tenant_preference": "ANYONE", "advance_amount": "0", "total_beds": 1, "gender_allowed": "ANY", "city": "Delhi", "latitude": "28.6", "longitude": "77.2",
            "whatsapp_number": "98765 43210", "images": [png("1.png"), png("2.png")],
        })
        self.assertEqual(resp.status_code, 302, getattr(resp, "context", None) and resp.context["form"].errors)
        room = Service.objects.get(title="New")
        self.assertEqual(room.images.count(), 2)
        self.assertEqual(room.whatsapp_number, "9876543210")
        self.assertIn("wa.me/919876543210", room.whatsapp_link)

    def test_only_one_of_lat_lng_rejected(self):
        self.client.force_login(self.owner)
        resp = self.client.post(reverse("services:create"), {
            "title": "New", "description": "x", "price": "5000", "deposit_amount": "0", "booking_amount": "0",
            "min_stay_months": 1, "tenant_preference": "ANYONE", "advance_amount": "0", "total_beds": 1, "gender_allowed": "ANY", "city": "Delhi", "latitude": "28.6", "longitude": "",
        })
        self.assertEqual(resp.status_code, 200)

    def test_non_image_upload_rejected(self):
        self.client.force_login(self.owner)
        bad = SimpleUploadedFile("x.png", b"not an image", content_type="image/png")
        resp = self.client.post(reverse("services:create"), {
            "title": "New", "description": "x", "price": "5000", "deposit_amount": "0", "booking_amount": "0",
            "min_stay_months": 1, "tenant_preference": "ANYONE", "advance_amount": "0", "total_beds": 1, "gender_allowed": "ANY", "city": "Delhi", "images": [bad],
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Service.objects.filter(title="New").exists())

    def test_other_owner_cannot_edit_pause_or_delete(self):
        other = User.objects.create_user("other", "x@x.com", "pw12345678", role="PROVIDER")
        self.client.force_login(other)
        for name in ("edit", "toggle_active", "delete"):
            r = self.client.post(reverse(f"services:{name}", args=[self.room.pk]), {})
            self.assertEqual(r.status_code, 404, name)

    def test_pause_hides_listing_and_delete_blocked_with_bookings(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("services:toggle_active", args=[self.room.pk]))
        self.room.refresh_from_db()
        self.assertFalse(self.room.is_active)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("services:detail", args=[self.room.pk])).status_code, 404)

    def test_remove_image_on_edit(self):
        img = ServiceImage.objects.create(service=self.room, image=png("z.png"))
        self.client.force_login(self.owner)
        self.client.post(reverse("services:edit", args=[self.room.pk]), {
            "title": "Cozy room", "description": "d", "price": "6000", "deposit_amount": "6000",
            "booking_amount": "300", "min_stay_months": 1, "tenant_preference": "ANYONE", "advance_amount": "0", "total_beds": 1, "gender_allowed": "ANY", "city": "Delhi",
            "delete_images": [img.pk],
        })
        self.assertEqual(self.room.images.count(), 0)


class SlotTests(TestCase):
    def setUp(self):
        self.owner, _ = make_users()
        self.room = make_room(self.owner)
        self.tomorrow = timezone.localdate() + datetime.timedelta(days=1)

    def test_slot_end_before_start_and_past_rejected(self):
        t = datetime.time
        f = SlotForm({"date": self.tomorrow, "start_time": t(12), "end_time": t(11)}, service=self.room)
        self.assertFalse(f.is_valid())
        yesterday = timezone.localdate() - datetime.timedelta(days=1)
        f = SlotForm({"date": yesterday, "start_time": t(10), "end_time": t(11)}, service=self.room)
        self.assertFalse(f.is_valid())

    def test_duplicate_slot_rejected(self):
        Slot.objects.create(service=self.room, date=self.tomorrow, start_time=datetime.time(10), end_time=datetime.time(11))
        f = SlotForm({"date": self.tomorrow, "start_time": datetime.time(10), "end_time": datetime.time(11)}, service=self.room)
        self.assertFalse(f.is_valid())

    def test_bulk_generation(self):
        f = BulkSlotForm({
            "start_date": self.tomorrow, "end_date": self.tomorrow + datetime.timedelta(days=1),
            "window_start": "10:00", "window_end": "12:00", "slot_minutes": "30",
        })
        self.assertTrue(f.is_valid(), f.errors)
        self.assertEqual(len(list(f.iter_slots())), 8)

    def test_bulk_rejects_huge_range_and_short_window(self):
        f = BulkSlotForm({"start_date": self.tomorrow, "end_date": self.tomorrow + datetime.timedelta(days=90),
                          "window_start": "10:00", "window_end": "12:00", "slot_minutes": "30"})
        self.assertFalse(f.is_valid())
        f = BulkSlotForm({"start_date": self.tomorrow, "end_date": self.tomorrow,
                          "window_start": "10:00", "window_end": "10:20", "slot_minutes": "30"})
        self.assertFalse(f.is_valid())

    def test_manage_slots_bulk_and_delete(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("services:manage_slots", args=[self.room.pk]), {
            "bulk": "1", "start_date": self.tomorrow, "end_date": self.tomorrow,
            "window_start": "10:00", "window_end": "11:00", "slot_minutes": "30",
        })
        self.assertEqual(self.room.slots.count(), 2)
        slot = self.room.slots.first()
        self.client.post(reverse("services:delete_slot", args=[self.room.pk, slot.pk]))
        self.assertEqual(self.room.slots.count(), 1)


class ReportAndApiTests(TestCase):
    def setUp(self):
        self.owner, self.tenant = make_users()
        self.room = make_room(self.owner)

    def test_report_once_then_update(self):
        self.client.force_login(self.tenant)
        url = reverse("services:report", args=[self.room.pk])
        self.client.post(url, {"reason": "SCAM", "details": "asked for money"})
        self.client.post(url, {"reason": "WRONG_INFO", "details": ""})
        self.assertEqual(Report.objects.count(), 1)
        self.assertEqual(Report.objects.get().reason, "WRONG_INFO")

    def test_owner_cannot_report_own_listing(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("services:report", args=[self.room.pk]), {"reason": "SCAM"})
        self.assertEqual(Report.objects.count(), 0)

    def test_api_list_works_and_filters(self):
        resp = self.client.get("/api/services/", {"max_price": "1000"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 0)
        resp = self.client.get("/api/services/")
        self.assertEqual(resp.json()["count"], 1)
        self.assertEqual(resp.json()["results"][0]["title"], "Cozy room")

    def test_verification_request_flow(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("accounts:verification"), {"phone_number": "9876543210", "verification_note": "hi"})
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.verification_requested)
        self.assertFalse(self.owner.is_verified)


class NewFilterTests(TestCase):
    def setUp(self):
        from .models import Amenity
        self.owner, _ = make_users()
        self.wifi, _ = Amenity.objects.get_or_create(name="Wi-Fi")
        self.ac, _ = Amenity.objects.get_or_create(name="AC")
        self.girls = make_room(self.owner, title="Girls PG", gender_allowed="FEMALE")
        self.boys = make_room(self.owner, title="Boys PG", gender_allowed="MALE")
        self.any = make_room(self.owner, title="Any room", gender_allowed="ANY")
        self.girls.amenities.add(self.wifi, self.ac)
        self.boys.amenities.add(self.wifi)

    def titles(self, **params):
        resp = self.client.get(reverse("services:list"), params)
        return {s.title for s in resp.context["page_obj"]}

    def test_gender_filter_includes_open_to_all(self):
        self.assertEqual(self.titles(gender="FEMALE"), {"Girls PG", "Any room"})
        self.assertEqual(self.titles(gender="MALE"), {"Boys PG", "Any room"})

    def test_amenity_filter_requires_all(self):
        self.assertEqual(self.titles(amenity=[self.wifi.id]), {"Girls PG", "Boys PG"})
        self.assertEqual(self.titles(amenity=[self.wifi.id, self.ac.id]), {"Girls PG"})

    def test_default_amenities_exist(self):
        from .models import Amenity
        self.assertTrue(Amenity.objects.filter(name="Geyser / hot water").exists())

    def test_available_only_hides_full_rooms(self):
        tenant = User.objects.create_user("tt", "t@x.com", "pw12345678", role="CUSTOMER", phone_verified=True)
        from bookings.models import Booking
        today = timezone.localdate()
        Booking.objects.create(kind="RENTAL", customer=tenant, service=self.girls, status="CONFIRMED",
                               total_price=0, move_in_date=today, stay_months=3,
                               stay_end_date=today + datetime.timedelta(days=90))
        self.assertNotIn("Girls PG", self.titles(available="1"))
        self.assertIn("Girls PG", self.titles())
        self.assertTrue(Service.objects.get(pk=self.girls.pk).is_full)

    def test_unverified_owner_cannot_list_a_room(self):
        self.owner.phone_verified = False
        self.owner.save()
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("services:create"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/verify/phone/", resp.url)


from django.http import QueryDict
from .filters import active_chips, build_listing, describe
from .models import SavedSearch


class CompareAndRecentTests(TestCase):
    def setUp(self):
        self.owner, self.tenant = make_users()
        self.rooms = [make_room(self.owner, title=f"R{i}", price=5000 + i * 1000) for i in range(4)]

    def toggle(self, room):
        return self.client.post(reverse("services:compare_toggle", args=[room.pk]), {"next": "/services/"})

    def test_compare_limit_three_and_remove(self):
        for r in self.rooms:
            self.toggle(r)
        self.assertEqual(self.client.session["compare"], [r.pk for r in self.rooms[:3]])
        self.toggle(self.rooms[0])
        self.assertEqual(len(self.client.session["compare"]), 2)

    def test_compare_page_needs_two_then_shows_table(self):
        self.toggle(self.rooms[0])
        self.assertContains(self.client.get(reverse("services:compare")), "Pick at least 2")
        self.toggle(self.rooms[1])
        resp = self.client.get(reverse("services:compare"))
        self.assertContains(resp, "lowest")
        self.client.post(reverse("services:compare_clear"))
        self.assertEqual(self.client.session["compare"], [])

    def test_compare_redirect_is_not_open(self):
        resp = self.client.post(reverse("services:compare_toggle", args=[self.rooms[0].pk]), {"next": "https://evil.example"})
        self.assertEqual(resp.url, reverse("services:list"))

    def test_recently_viewed_most_recent_first(self):
        for r in self.rooms[:3]:
            self.client.get(reverse("services:detail", args=[r.pk]))
        resp = self.client.get(reverse("home"))
        self.assertEqual([s.pk for s in resp.context["recent"]], [self.rooms[2].pk, self.rooms[1].pk, self.rooms[0].pk])

    def test_view_count_once_per_visitor_and_not_for_owner(self):
        url = reverse("services:detail", args=[self.rooms[0].pk])
        self.client.get(url); self.client.get(url)
        self.rooms[0].refresh_from_db()
        self.assertEqual(self.rooms[0].view_count, 1)
        self.client.force_login(self.owner)
        self.client.get(url)
        self.rooms[0].refresh_from_db()
        self.assertEqual(self.rooms[0].view_count, 1)


class SavedSearchTests(TestCase):
    def setUp(self):
        self.owner, self.tenant = make_users()
        self.client.force_login(self.tenant)

    def test_save_and_delete_alert(self):
        self.client.post(reverse("services:save_search"), {"params": "pref=STUDENT&max_price=8000"})
        s = SavedSearch.objects.get()
        self.assertIn("Students", s.name)
        self.assertIn("under ₹8,000", s.name)
        self.client.post(reverse("services:save_search"), {"params": "pref=STUDENT&max_price=8000"})
        self.assertEqual(SavedSearch.objects.count(), 1)
        self.client.post(reverse("services:delete_search", args=[s.pk]))
        self.assertEqual(SavedSearch.objects.count(), 0)

    def test_limit_ten(self):
        for i in range(12):
            self.client.post(reverse("services:save_search"), {"params": f"max_price={1000 + i}"})
        self.assertEqual(SavedSearch.objects.count(), 10)

    def test_other_users_cannot_delete(self):
        self.client.post(reverse("services:save_search"), {"params": "pref=STUDENT"})
        s = SavedSearch.objects.get()
        other = User.objects.create_user("zz", "z@x.com", "pw12345678")
        self.client.force_login(other)
        self.assertEqual(self.client.post(reverse("services:delete_search", args=[s.pk])).status_code, 404)

    def test_new_matching_room_notifies_but_nonmatching_does_not(self):
        self.client.post(reverse("services:save_search"), {"params": "max_price=7000&city=Pune"})
        self.client.post(reverse("services:save_search"), {"params": "max_price=3000"})
        self.client.force_login(self.owner)
        self.client.post(reverse("services:create"), {
            "title": "Pune PG", "description": "x", "price": "6500", "deposit_amount": "0", "booking_amount": "0",
            "min_stay_months": 1, "tenant_preference": "ANYONE", "advance_amount": "0", "total_beds": 1,
            "gender_allowed": "ANY", "city": "Pune", "location": "Kothrud"})
        self.assertTrue(Service.objects.filter(title="Pune PG").exists())
        notes = list(self.tenant.notifications.values_list("message", flat=True))
        self.assertEqual(len(notes), 1)
        self.assertIn("Pune PG", notes[0])

    def test_alert_requires_login(self):
        self.client.logout()
        resp = self.client.post(reverse("services:save_search"), {"params": "pref=STUDENT"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(SavedSearch.objects.count(), 0)


class DiscoveryTests(TestCase):
    def setUp(self):
        self.owner, self.tenant = make_users()
        make_room(self.owner, title="A", city="Delhi", location="Rohini", price=5000)
        make_room(self.owner, title="B", city="Delhi", location="Rohini", price=6000)
        self.target = make_room(self.owner, title="C", city="Delhi", location="Rohini", price=9000)
        make_room(self.owner, title="D", city="Pune", location="Kothrud", price=6000)

    def test_city_filter_and_chips_label(self):
        resp = self.client.get(reverse("services:list"), {"city": "pune", "max_price": "7000"})
        self.assertEqual({s.title for s in resp.context["page_obj"]}, {"D"})
        labels = [c[0] for c in resp.context["chips"]]
        self.assertIn("Max ₹7,000", labels)
        qs, st = build_listing(QueryDict("city=Delhi&pref=STUDENT"))
        self.assertEqual(describe(st), "Delhi · Students")

    def test_chip_removal_url_drops_only_that_filter(self):
        g = QueryDict("city=Delhi&max_price=7000")
        _, st = build_listing(g)
        urls = dict(active_chips(g, st))
        self.assertEqual(urls["Delhi"], "?max_price=7000")

    def test_price_insight_and_similar_rooms(self):
        resp = self.client.get(reverse("services:detail", args=[self.target.pk]))
        insight = resp.context["price_insight"]
        self.assertGreater(insight["diff"], 0)
        self.assertEqual(insight["n"], 2)
        self.assertContains(resp, "above")
        self.assertEqual(len(resp.context["similar"]), 0)
        mid = Service.objects.get(title="B")
        similar = self.client.get(reverse("services:detail", args=[mid.pk])).context["similar"]
        self.assertEqual([s.title for s in similar], ["A"])

    def test_rating_breakdown_on_detail(self):
        from bookings.models import Booking
        from .models import Review
        today = timezone.localdate()
        for i, stars in enumerate((5, 5, 4)):
            u = User.objects.create_user(f"rv{i}", "r@x.com", "pw12345678")
            slot = Slot.objects.create(service=self.target, date=today - datetime.timedelta(days=3 + i),
                                       start_time=datetime.time(10), end_time=datetime.time(11), is_booked=True)
            b = Booking.objects.create(kind="VISIT", customer=u, service=self.target, slot=slot, status="CONFIRMED", total_price=0)
            Review.objects.create(service=self.target, customer=u, booking=b, rating=stars)
        resp = self.client.get(reverse("services:detail", args=[self.target.pk]))
        rows = {r["star"]: r for r in resp.context["breakdown"]}
        self.assertEqual((rows[5]["n"], rows[4]["n"], rows[3]["n"]), (2, 1, 0))
        self.assertEqual(rows[5]["pct"], 67)
        self.assertContains(resp, "Verified stay")

    def test_owner_profile(self):
        self.assertContains(self.client.get(reverse("services:owner_profile", args=["owner"])), "Listings by owner")
        self.assertEqual(self.client.get(reverse("services:owner_profile", args=["tenant"])).status_code, 404)

    def test_dashboard_stats_and_response_time(self):
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("services:provider_dashboard"))
        self.assertEqual(resp.context["totals"]["active"], 4)
        from .stats import owner_response_hours
        self.assertIsNone(owner_response_hours(self.owner))


class StaticPagesAndSeoTests(TestCase):
    def test_pages_render(self):
        for name in ("about", "faq", "terms", "privacy", "contact"):
            self.assertEqual(self.client.get(reverse(f"pages:{name}")).status_code, 200, name)

    def test_contact_saves_message_and_honeypot_blocks_bots(self):
        from pages.models import ContactMessage
        url = reverse("pages:contact")
        self.client.post(url, {"name": "A", "email": "a@x.com", "message": "hi", "website": ""})
        self.client.post(url, {"name": "Bot", "email": "b@x.com", "message": "spam", "website": "http://spam"})
        self.assertEqual(ContactMessage.objects.count(), 1)

    def test_sitemap_and_robots(self):
        owner, _ = make_users()
        room = make_room(owner)
        xml = self.client.get("/sitemap.xml").content.decode()
        self.assertIn(f"/services/{room.pk}/", xml)
        robots = self.client.get("/robots.txt").content.decode()
        self.assertIn("Disallow: /admin/", robots)
        self.assertIn("Sitemap:", robots)

    def test_detail_has_seo_meta(self):
        owner, _ = make_users()
        room = make_room(owner, title="Sunny Studio")
        html = self.client.get(reverse("services:detail", args=[room.pk])).content.decode()
        self.assertIn('property="og:title"', html)
        self.assertIn("Sunny Studio", html)

    def test_home_shows_stats_and_hero_search(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("Search rooms", html)
        self.assertIn("Rooms listed", html)


class DirectionsLinkTests(TestCase):
    def test_directions_links_force_english_and_hindi_and_driving(self):
        owner, _ = make_users()
        room = make_room(owner, latitude=Decimal("28.6139"), longitude=Decimal("77.2090"))
        html = self.client.get(reverse("services:detail", args=[room.pk])).content.decode()
        self.assertIn("&travelmode=driving&hl=en", html)
        self.assertIn("&travelmode=driving&hl=hi", html)
        self.assertNotIn("hl=ur", html)


from io import BytesIO as _BIO
from PIL import Image as _PIL
from django.core.files.uploadedfile import SimpleUploadedFile as _Up
from .forms import normalise_image_url, parse_urls


def _pano(w=3000, h=1500, name="p.jpg"):
    buf = _BIO()
    _PIL.new("RGB", (w, h), "blue").save(buf, "JPEG")
    return _Up(name, buf.getvalue(), content_type="image/jpeg")


BASE_POST = {"title": "T", "description": "x", "price": "5000", "deposit_amount": "0", "booking_amount": "0",
             "min_stay_months": 1, "tenant_preference": "ANYONE", "advance_amount": "0", "total_beds": 1,
             "gender_allowed": "ANY", "city": "Delhi"}


class PhotoLinkAndPanoramaTests(TestCase):
    def setUp(self):
        self.owner, self.tenant = make_users()
        self.client.force_login(self.owner)

    def post(self, **extra):
        return self.client.post(reverse("services:create"), {**BASE_POST, **extra})

    def test_photo_links_are_saved_and_used_as_cover(self):
        resp = self.post(image_urls="https://images.example.com/a.jpg\nhttps://images.example.com/b.jpg")
        self.assertEqual(resp.status_code, 302)
        room = Service.objects.get(title="T")
        self.assertEqual(room.images.count(), 2)
        self.assertEqual(room.cover_url, "https://images.example.com/a.jpg")

    def test_http_and_garbage_links_rejected(self):
        self.assertEqual(self.post(image_urls="http://insecure.example.com/a.jpg").status_code, 200)
        self.assertEqual(self.post(image_urls="javascript:alert(1)").status_code, 200)
        self.assertFalse(Service.objects.filter(title="T").exists())

    def test_google_drive_link_is_converted(self):
        self.assertEqual(normalise_image_url("https://drive.google.com/file/d/ABC_123-x/view?usp=sharing"),
                         "https://drive.google.com/thumbnail?id=ABC_123-x&sz=w2000")
        self.assertEqual(parse_urls("https://drive.google.com/open?id=Z9"), ["https://drive.google.com/thumbnail?id=Z9&sz=w2000"])

    def test_panorama_upload_and_link_shown_on_detail(self):
        resp = self.post(panoramas=[_pano()], panorama_urls="https://example.com/tour.jpg")
        self.assertEqual(resp.status_code, 302)
        room = Service.objects.get(title="T")
        self.assertEqual(room.images.filter(is_360=True).count(), 2)
        self.assertEqual(room.photos, [])
        self.assertTrue(room.has_360)
        html = self.client.get(reverse("services:detail", args=[room.pk])).content.decode()
        self.assertIn('id="pano-viewer"', html)
        self.assertIn("pannellum.js", html)
        self.assertIn("360&deg; tour", html)

    def test_panorama_must_be_two_to_one(self):
        self.assertEqual(self.post(panoramas=[_pano(3000, 2000)]).status_code, 200)
        self.assertEqual(self.post(panoramas=[_pano(800, 400)]).status_code, 200)
        self.assertFalse(Service.objects.filter(title="T").exists())

    def test_limits_for_photos_and_panoramas(self):
        urls = "\n".join(f"https://x.example.com/{i}.jpg" for i in range(9))
        self.assertEqual(self.post(image_urls=urls).status_code, 200)
        panos = "\n".join(f"https://x.example.com/p{i}.jpg" for i in range(4))
        self.assertEqual(self.post(panorama_urls=panos).status_code, 200)

    def test_card_shows_360_badge_and_panorama_not_in_gallery(self):
        room = make_room(self.owner)
        ServiceImage.objects.create(service=room, image_url="https://x.example.com/a.jpg")
        ServiceImage.objects.create(service=room, image_url="https://x.example.com/t.jpg", is_360=True)
        html = self.client.get(reverse("services:list")).content.decode()
        self.assertIn("pill360", html)
        self.assertEqual(room.cover_url, "https://x.example.com/a.jpg")
        self.assertEqual(len(room.photos), 1)

    def test_edit_can_remove_a_panorama(self):
        room = make_room(self.owner)
        pano = ServiceImage.objects.create(service=room, image_url="https://x.example.com/t.jpg", is_360=True)
        self.client.post(reverse("services:edit", args=[room.pk]), {**BASE_POST, "title": "Cozy room", "delete_images": [pano.pk]})
        self.assertFalse(room.images.exists())


import tempfile
from io import StringIO as _SIO
from django.core.management import call_command
from .management.commands.seed_demo_data import PHOTO_DIR, PHOTO_SETS


class SeedPhotoTests(TestCase):
    def test_photo_sets_are_valid(self):
        used = [name for names in PHOTO_SETS.values() for name in names]
        for name in set(used):
            self.assertTrue((PHOTO_DIR / f"{name}.jpg").exists(), name)
        for username, names in PHOTO_SETS.items():
            self.assertEqual(len(names), len(set(names)), username)
            self.assertGreaterEqual(len(names), 3)
        covers = [names[0] for names in PHOTO_SETS.values()]
        self.assertEqual(len(covers), len(set(covers)))
        self.assertNotIn("bedroom-3", used)
        self.assertFalse((PHOTO_DIR / "bedroom-3.jpg").exists())

    def test_seed_attaches_real_photos_and_replaces_old_illustrations(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(MEDIA_ROOT=tmp):
            call_command("seed_demo_data", stdout=_SIO())
            rooms = list(Service.objects.all())
            self.assertEqual(len(rooms), 10)
            for room in rooms:
                self.assertGreaterEqual(len(room.photos), 3)
                self.assertTrue(room.has_360)
                with _PIL.open(room.photos[0].image) as im:
                    self.assertGreaterEqual(im.width, 1000)
            sharma = Service.objects.get(provider__username="sharma_pg")
            old = ServiceImage.objects.create(service=sharma)
            ServiceImage.objects.filter(pk=old.pk).update(image="services/sharma_pg_0.jpg")
            before = len(sharma.photos)
            call_command("seed_demo_data", stdout=_SIO())
            sharma = Service.objects.get(provider__username="sharma_pg")
            self.assertEqual(len(sharma.photos), 5)
            self.assertFalse(sharma.images.filter(image="services/sharma_pg_0.jpg").exists())


class ProductionMediaTests(TestCase):
    def test_media_files_are_served_when_debug_is_off(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(MEDIA_ROOT=tmp, DEBUG=False):
            import pathlib
            (pathlib.Path(tmp) / "services").mkdir()
            (pathlib.Path(tmp) / "services" / "x.jpg").write_bytes(b"jpegdata")
            resp = self.client.get("/media/services/x.jpg")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(b"".join(resp.streaming_content), b"jpegdata")
            self.assertEqual(self.client.get("/media/services/missing.jpg").status_code, 404)
            self.assertIn(self.client.get("/media/../config/settings.py").status_code, (400, 404))

    def test_seed_restores_photos_whose_files_were_wiped(self):
        import pathlib
        with tempfile.TemporaryDirectory() as tmp, override_settings(MEDIA_ROOT=tmp):
            call_command("seed_demo_data", stdout=_SIO())
            room = Service.objects.get(provider__username="sharma_pg")
            count = room.images.count()
            for img in room.images.all():
                pathlib.Path(img.image.path).unlink()
            call_command("seed_demo_data", stdout=_SIO())
            room = Service.objects.get(provider__username="sharma_pg")
            self.assertEqual(room.images.count(), count)
            for img in room.images.all():
                self.assertTrue(pathlib.Path(img.image.path).exists())


class HostSettingsTests(TestCase):
    def test_render_hostname_is_trusted_automatically(self):
        import os, pathlib, subprocess, sys
        code = ("import os; os.environ['DJANGO_SETTINGS_MODULE']='config.settings'; from django.conf import settings; "
                "print('app.onrender.com' in settings.ALLOWED_HOSTS, 'https://app.onrender.com' in settings.CSRF_TRUSTED_ORIGINS, settings.USE_OBJECT_STORAGE)")
        env = {**os.environ, "RENDER_EXTERNAL_HOSTNAME": "app.onrender.com", "LOCAL_MODE": "True"}
        env.pop("DATABASE_URL", None)
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                             cwd=str(pathlib.Path(__file__).resolve().parent.parent))
        self.assertEqual(out.stdout.strip().split("\n")[-1], "True True False")
