import datetime
import re
from io import BytesIO
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageFilter
import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from django.core.files.base import ContentFile

from bookings.models import Booking
from services.demo_images import panorama_image
from services.models import Amenity, Category, Review, Service, ServiceImage, Slot

User = get_user_model()

CATEGORIES = ["Single Room (PG)", "Shared Room", "1RK / Studio", "Family Room", "Independent Room"]

OWNERS = [
    {"username": "sharma_pg", "first_name": "Ramesh", "category": "Single Room (PG)",
     "title": "Cozy Single Room near Delhi University", "price": 6500, "deposit": 6500,
     "min_stay": 3, "furnished": True, "pref": "STUDENT", "location": "Kamla Nagar, Delhi",
     "description": "Well-lit single room, walking distance from North Campus. Wi-Fi, meals, and laundry included. Perfect for students."},
    {"username": "verma_homes", "first_name": "Sunita", "category": "Family Room",
     "title": "Spacious Family Room with Kitchen Access", "price": 12000, "deposit": 12000,
     "min_stay": 6, "furnished": True, "pref": "FAMILY", "location": "Rohini, Delhi",
     "description": "Independent room with attached kitchen access, ideal for a small family. Quiet residential lane, near school and market."},
    {"username": "cantt_stay", "first_name": "Colonel Anand", "category": "Independent Room",
     "title": "Defence-Friendly Room near Cantonment", "price": 8500, "deposit": 8000,
     "min_stay": 1, "furnished": True, "pref": "DEFENCE", "location": "Delhi Cantt",
     "description": "Independent room close to the cantonment area, flexible short-term stays for army personnel on posting. Secure locality with 24x7 water and power backup."},
    {"username": "gupta_pg_girls", "first_name": "Kavita", "category": "Shared Room",
     "title": "Shared Room for Girls - Budget Friendly", "price": 4500, "deposit": 4500,
     "min_stay": 2, "furnished": True, "pref": "STUDENT", "location": "Laxmi Nagar, Delhi",
     "description": "Twin-sharing room for female students, warden on premises, home-cooked meals, walking distance to metro station."},
    {"username": "mehta_studio", "first_name": "Ajay", "category": "1RK / Studio",
     "title": "Compact 1RK for Working Professionals", "price": 9500, "deposit": 9500,
     "min_stay": 3, "furnished": True, "pref": "WORKING_PROFESSIONAL", "location": "Dwarka, Delhi",
     "description": "Self-contained 1 room kitchen, private washroom, ideal for a working professional or small family. Near metro connectivity."},
    {"username": "singh_family_pg", "first_name": "Harpreet", "category": "Family Room",
     "title": "Affordable Room for Army Family", "price": 7000, "deposit": 7000,
     "min_stay": 1, "furnished": False, "pref": "DEFENCE", "location": "Dhaula Kuan, Delhi",
     "description": "Ground-floor independent room, well suited for army families needing flexible short or long stays near the cantonment."},
    {"username": "patel_pg", "first_name": "Jignesh", "category": "Single Room (PG)", "city": "Chandigarh",
     "title": "Sector 22 Boys PG with Meals", "price": 7500, "deposit": 7500,
     "min_stay": 3, "furnished": True, "pref": "STUDENT", "location": "Sector 22",
     "description": "Neat single-occupancy rooms for boys, three home-style meals a day, high-speed Wi-Fi and a study lounge. 5 minutes from Sector 17 market and the ISBT."},
    {"username": "iyer_homes", "first_name": "Lakshmi", "category": "1RK / Studio", "city": "Bengaluru",
     "title": "Sunny Studio near Koramangala Tech Parks", "price": 16500, "deposit": 33000,
     "min_stay": 6, "furnished": True, "pref": "WORKING_PROFESSIONAL", "location": "Koramangala",
     "description": "Fully furnished studio with modular kitchen, AC and high-speed internet. Ten-minute walk to cafes and tech parks. Lift, parking and 24x7 security."},
    {"username": "deshpande_pg", "first_name": "Meera", "category": "Shared Room", "city": "Pune",
     "title": "Girls PG near Kothrud - Safe & Homely", "price": 6000, "deposit": 6000,
     "min_stay": 2, "furnished": True, "pref": "STUDENT", "location": "Kothrud",
     "description": "Triple-sharing rooms for girls with a warden, CCTV, home-cooked meals and a quiet study room. Close to colleges and PMPML bus stops."},
    {"username": "rathore_haveli", "first_name": "Vikram", "category": "Independent Room", "city": "Jaipur",
     "title": "Heritage Haveli Room, Malviya Nagar", "price": 8000, "deposit": 8000,
     "min_stay": 1, "furnished": True, "pref": "ANYONE", "location": "Malviya Nagar",
     "description": "Spacious room in a restored haveli with a courtyard garden, attached bath and parking. Flexible stays for families, students and visiting professionals."},
]

EXTRAS = {
    "sharma_pg":       {"lat": 28.6825, "lng": 77.2050, "token": 300, "verified": True,  "whatsapp": "9876500001", "gender": "ANY", "beds": 2, "advance": 2000, "amenities": ["Wi-Fi", "Geyser / hot water", "Study table"]},
    "verma_homes":     {"lat": 28.7041, "lng": 77.1025, "token": 500, "verified": True,  "whatsapp": "", "gender": "ANY", "beds": 1, "advance": 3000, "amenities": ["Wi-Fi", "Parking", "Power backup"]},
    "cantt_stay":      {"lat": 28.5921, "lng": 77.1360, "token": 500, "verified": True,  "whatsapp": "9876500003", "gender": "MALE", "beds": 3, "advance": 2500, "amenities": ["Wi-Fi", "AC", "CCTV & security", "Meals included"]},
    "gupta_pg_girls":  {"lat": 28.6304, "lng": 77.2773, "token": 200, "verified": False, "whatsapp": "", "gender": "FEMALE", "beds": 4, "advance": 1500, "amenities": ["Wi-Fi", "Meals included", "Laundry", "CCTV & security"]},
    "mehta_studio":    {"lat": 28.5921, "lng": 77.0460, "token": 400, "verified": False, "whatsapp": "9876500005", "gender": "ANY", "beds": 1, "advance": 3000, "amenities": ["Wi-Fi", "AC", "Lift", "Housekeeping"]},
    "singh_family_pg": {"lat": 28.5913, "lng": 77.1660, "token": 0,   "verified": False, "whatsapp": "", "gender": "ANY", "beds": 2, "advance": 0, "amenities": ["Wi-Fi", "Parking", "Power backup"]},
    "patel_pg":        {"lat": 30.7333, "lng": 76.7794, "token": 300, "verified": True,  "whatsapp": "9876500007", "gender": "MALE", "beds": 6, "advance": 2000, "amenities": ["Wi-Fi", "Meals included", "Laundry", "CCTV & security", "Study table"]},
    "iyer_homes":      {"lat": 12.9352, "lng": 77.6245, "token": 500, "verified": True,  "whatsapp": "9876500008", "gender": "ANY", "beds": 1, "advance": 5000, "amenities": ["Wi-Fi", "AC", "Power backup", "Lift", "Housekeeping", "Parking"]},
    "deshpande_pg":    {"lat": 18.5074, "lng": 73.8077, "token": 200, "verified": True,  "whatsapp": "", "gender": "FEMALE", "beds": 5, "advance": 1500, "amenities": ["Wi-Fi", "Meals included", "Laundry", "Study table", "CCTV & security"]},
    "rathore_haveli":  {"lat": 26.8553, "lng": 75.8103, "token": 0,   "verified": False, "whatsapp": "9876500010", "gender": "ANY", "beds": 2, "advance": 2000, "amenities": ["Wi-Fi", "Parking", "Geyser / hot water", "Attached bathroom"]},
}

PHOTO_DIR = Path(settings.BASE_DIR) / "static" / "demo"

PHOTO_SETS = {
    "sharma_pg": ["bedroom-4", "living-1", "balcony-3", "bedroom-6", "balcony-1"],
    "verma_homes": ["bedroom-2", "living-2", "balcony-1", "bedroom-1", "balcony-4"],
    "cantt_stay": ["bedroom-5", "living-6", "balcony-2", "bedroom-2", "living-3"],
    "gupta_pg_girls": ["bedroom-6", "living-4", "balcony-4", "bedroom-4", "balcony-3"],
    "mehta_studio": ["living-6", "bedroom-4", "balcony-1", "living-7", "bedroom-2"],
    "singh_family_pg": ["living-5", "bedroom-1", "balcony-3", "bedroom-2", "balcony-2"],
    "patel_pg": ["living-7", "bedroom-5", "balcony-4", "bedroom-6"],
    "iyer_homes": ["living-3", "bedroom-1", "balcony-2", "living-6", "living-2"],
    "deshpande_pg": ["living-4", "bedroom-4", "balcony-3", "bedroom-6"],
    "rathore_haveli": ["living-1", "bedroom-6", "balcony-2", "living-5", "balcony-1"],
}


def prepared_photo(name):
    img = Image.open(PHOTO_DIR / f"{name}.jpg").convert("RGB")
    if img.width < 1280:
        img = img.resize((1280, round(img.height * 1280 / img.width)), Image.LANCZOS)
        img = img.filter(ImageFilter.UnsharpMask(radius=1.4, percent=70, threshold=2))
    buf = BytesIO()
    img.save(buf, "JPEG", quality=90, optimize=True)
    return buf.getvalue()


def drop_missing_files(service):
    for img in service.images.all():
        if img.image and not img.image.storage.exists(img.image.name):
            img.delete()


def attach_real_photos(service, username):
    drop_missing_files(service)
    for old in service.images.filter(is_360=False):
        if old.image and re.match(rf"^services/{username}_\d", old.image.name):
            old.image.delete(save=False)
            old.delete()
    if service.images.filter(is_360=False).exists():
        return
    for n, name in enumerate(PHOTO_SETS[username], 1):
        photo = ServiceImage(service=service)
        photo.image.save(f"{username}_p{n}.jpg", ContentFile(prepared_photo(name)), save=True)


REVIEW_TEXT = [
    (5, "Exactly as shown. The owner was friendly and the room was spotless."),
    (5, "Very safe locality and genuinely broker-free. Moved in without any hassle."),
    (4, "Good value for the price. Wi-Fi is fast, water supply is reliable."),
    (4, "Owner responds quickly and the visit was well organised."),
    (5, "Loved the place - quiet, clean and close to everything I needed."),
    (4, "Nice room. Would have liked a bit more storage but overall happy."),
]
DEMO_TENANTS = [("riya_s", "Riya"), ("arjun_k", "Arjun"), ("neha_p", "Neha")]


class Command(BaseCommand):
    help = "Seed the database with demo room categories, owners, room listings, and open visit slots."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush", action="store_true", help="Delete existing demo data before seeding."
        )

    def handle(self, *args, **options):
        if options["flush"]:
            Service.objects.filter(provider__username__in=[o["username"] for o in OWNERS]).delete()
            User.objects.filter(username__in=[o["username"] for o in OWNERS]).delete()
            self.stdout.write(self.style.WARNING("Cleared existing demo data."))

        categories = {}
        for name in CATEGORIES:
            category, _ = Category.objects.get_or_create(name=name)
            categories[name] = category
        self.stdout.write(self.style.SUCCESS(f"Ensured {len(categories)} room categories."))

        created_services = 0
        today = timezone.localdate()

        for info in OWNERS:
            owner, created = User.objects.get_or_create(
                username=info["username"],
                defaults={
                    "first_name": info["first_name"],
                    "email": f"{info['username']}@example.com",
                    "role": User.Role.PROVIDER,
                },
            )
            if created:
                owner.set_password("demopass123")
            extra = EXTRAS[info["username"]]
            owner.is_verified = extra["verified"]
            owner.phone_number = "+91987650" + f"{sum(ord(c) for c in info['username']) % 10000:04d}"
            owner.phone_verified = True
            owner.email_verified = True
            owner.save()

            service, created = Service.objects.get_or_create(
                provider=owner,
                title=info["title"],
                defaults={
                    "category": categories[info["category"]],
                    "description": info["description"],
                    "price": info["price"],
                    "deposit_amount": info["deposit"],
                    "min_stay_months": info["min_stay"],
                    "is_furnished": info["furnished"],
                    "tenant_preference": info["pref"],
                    "city": info.get("city", "Delhi"),
                    "location": info["location"].replace(", Delhi", ""),
                    "latitude": extra["lat"],
                    "longitude": extra["lng"],
                    "booking_amount": extra["token"],
                    "whatsapp_number": extra["whatsapp"],
                    "gender_allowed": extra["gender"],
                    "total_beds": extra["beds"],
                    "advance_amount": extra["advance"],
                    "is_active": True,
                },
            )
            if created:
                created_services += 1
            amenity_objs = [Amenity.objects.get_or_create(name=n)[0] for n in extra["amenities"]]
            service.amenities.set(amenity_objs)

            if created:
                service.view_count = random.randint(40, 420)
                service.save(update_fields=["view_count"])
            attach_real_photos(service, info["username"])
            if not service.images.filter(is_360=True).exists():
                palette = sum(ord(c) for c in info["username"]) % 5
                tour = ServiceImage(service=service, is_360=True)
                tour.image.save(f"{info['username']}_360.jpg", ContentFile(panorama_image(palette, seed=service.pk)), save=True)

            for day_offset in range(1, 6):
                slot_date = today + datetime.timedelta(days=day_offset)
                for hour in random.sample([10, 12, 15, 17], k=2):
                    Slot.objects.get_or_create(
                        service=service,
                        date=slot_date,
                        start_time=datetime.time(hour, 0),
                        defaults={"end_time": datetime.time(hour + 1, 0)},
                    )

        tenants = []
        for uname, first in DEMO_TENANTS:
            t, made = User.objects.get_or_create(username=uname, defaults={
                "first_name": first, "email": f"{uname}@example.com", "role": User.Role.CUSTOMER})
            if made:
                t.set_password("demopass123")
            t.phone_number = "+91991100" + f"{sum(ord(c) for c in uname) % 10000:04d}"
            t.phone_verified = t.email_verified = True
            t.save()
            tenants.append(t)
        for idx, service in enumerate(Service.objects.filter(provider__username__in=[o["username"] for o in OWNERS])):
            for n in range(2):
                tenant = tenants[(idx + n) % len(tenants)]
                past = today - datetime.timedelta(days=9 + n * 6 + idx)
                slot, _ = Slot.objects.get_or_create(service=service, date=past, start_time=datetime.time(11, 0),
                                                      defaults={"end_time": datetime.time(12, 0), "is_booked": True})
                booking, _ = Booking.objects.get_or_create(
                    slot=slot, defaults=dict(kind="VISIT", customer=tenant, service=service,
                                             status="CONFIRMED", total_price=0))
                rating, text = REVIEW_TEXT[(idx * 2 + n) % len(REVIEW_TEXT)]
                Review.objects.get_or_create(booking=booking, defaults=dict(
                    service=service, customer=booking.customer, rating=rating, comment=text))

        self.stdout.write(self.style.SUCCESS(
            f"Seed complete: {created_services} new room listings created across {len(OWNERS)} owners, "
            f"with open visit slots for the next 5 days."
        ))
        self.stdout.write("Demo owner login: any of the usernames above, password 'demopass123'.")
