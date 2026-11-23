import datetime
import re

from django.core.validators import URLValidator
from django.core.exceptions import ValidationError as DjangoValidationError

from django import forms
from django.utils import timezone

from .models import Report, Review, Service, Slot

MAX_IMAGES_PER_ROOM = 8
MAX_IMAGE_MB = 5
MAX_PANORAMAS = 3
MAX_PANORAMA_MB = 15


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"accept": "image/*"}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_clean = super().clean
        if isinstance(data, (list, tuple)):
            cleaned = [single_clean(d, initial) for d in data]
        else:
            cleaned = [single_clean(data, initial)]
        return [f for f in cleaned if f]


def normalise_image_url(raw):
    raw = raw.strip()
    m = re.search(r"drive\.google\.com/file/d/([\w-]+)", raw) or re.search(r"drive\.google\.com/open\?id=([\w-]+)", raw)
    if m:
        return f"https://drive.google.com/thumbnail?id={m.group(1)}&sz=w2000"
    return raw


def parse_urls(text):
    urls = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        url = normalise_image_url(line)
        if not url.lower().startswith("https://"):
            raise forms.ValidationError(f"Only secure https:// links are allowed: {line[:60]}")
        try:
            URLValidator(schemes=["https"])(url)
        except DjangoValidationError:
            raise forms.ValidationError(f"That doesn't look like a valid link: {line[:60]}")
        urls.append(url)
    return urls


class ServiceForm(forms.ModelForm):
    images = MultipleImageField(
        required=False,
        label=f"Upload photos (up to {MAX_IMAGES_PER_ROOM}, max {MAX_IMAGE_MB} MB each)",
    )
    image_urls = forms.CharField(
        required=False, label="Or paste photo links (one per line)",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "https://images.example.com/room1.jpg"}),
        help_text="Direct image links, or a public Google Drive file link. Google Photos album links don't work - download the photo and upload it instead.",
    )
    panoramas = MultipleImageField(
        required=False,
        label=f"360° photos (up to {MAX_PANORAMAS}, max {MAX_PANORAMA_MB} MB each)",
        help_text="Equirectangular 2:1 panoramas from a 360° camera or a phone panorama / Google Street View app.",
    )
    panorama_urls = forms.CharField(
        required=False, label="Or paste 360° photo links (one per line)",
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "https://example.com/living-room-360.jpg"}),
    )

    class Meta:
        model = Service
        fields = [
            "category", "title", "description", "price", "deposit_amount", "advance_amount",
            "booking_amount", "total_beds", "gender_allowed", "min_stay_months", "is_furnished",
            "tenant_preference", "amenities", "city", "location", "whatsapp_number", "latitude", "longitude",
        ]
        labels = {
            "title": "Room title",
            "price": "Monthly rent (₹)",
            "deposit_amount": "Security deposit (₹)",
            "booking_amount": "Visit booking amount (₹)",
            "advance_amount": "Room advance to reserve (₹)",
            "total_beds": "Number of beds / tenants",
            "gender_allowed": "Open to",
            "min_stay_months": "Minimum stay (months)",
            "is_furnished": "Furnished?",
            "tenant_preference": "Best suited for",
            "city": "City",
            "location": "Locality / area",
            "whatsapp_number": "WhatsApp number (optional, shown publicly)",
        }
        widgets = {
            "latitude": forms.HiddenInput(),
            "longitude": forms.HiddenInput(),
            "description": forms.Textarea(attrs={"rows": 5}),
            "amenities": forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].required = False
        self.fields["category"].empty_label = "General (no specific type)"

    def clean_price(self):
        price = self.cleaned_data["price"]
        if price <= 0:
            raise forms.ValidationError("Rent must be more than zero.")
        return price

    def clean_whatsapp_number(self):
        raw = re.sub(r"[\s\-()]", "", self.cleaned_data.get("whatsapp_number") or "")
        if raw and not re.fullmatch(r"\+?\d{10,14}", raw):
            raise forms.ValidationError("Enter a valid number, e.g. 9876543210 or +919876543210.")
        return raw

    def clean_images(self):
        files = self.cleaned_data.get("images") or []
        existing = self.instance.images.filter(is_360=False).count() if self.instance.pk else 0
        if existing + len(files) > MAX_IMAGES_PER_ROOM:
            raise forms.ValidationError(
                f"A room can have at most {MAX_IMAGES_PER_ROOM} photos "
                f"({existing} already uploaded)."
            )
        for f in files:
            if f.size > MAX_IMAGE_MB * 1024 * 1024:
                raise forms.ValidationError(f"{f.name} is larger than {MAX_IMAGE_MB} MB.")
        return files

    def clean_image_urls(self):
        return parse_urls(self.cleaned_data.get("image_urls"))

    def clean_panorama_urls(self):
        return parse_urls(self.cleaned_data.get("panorama_urls"))

    def clean_panoramas(self):
        files = self.cleaned_data.get("panoramas") or []
        for f in files:
            if f.size > MAX_PANORAMA_MB * 1024 * 1024:
                raise forms.ValidationError(f"{f.name} is larger than {MAX_PANORAMA_MB} MB.")
            width, height = f.image.size
            if width < 1500 or not 1.9 <= width / height <= 2.1:
                raise forms.ValidationError(f"{f.name} must be a 360° panorama with a 2:1 shape (for example 4096x2048).")
        return files

    def clean(self):
        cleaned = super().clean()
        existing = self.instance.images.filter(is_360=False).count() if self.instance.pk else 0
        existing_360 = self.instance.images.filter(is_360=True).count() if self.instance.pk else 0
        photos = len(cleaned.get("images") or []) + len(cleaned.get("image_urls") or [])
        panos = len(cleaned.get("panoramas") or []) + len(cleaned.get("panorama_urls") or [])
        if existing + photos > MAX_IMAGES_PER_ROOM:
            raise forms.ValidationError(f"A room can have at most {MAX_IMAGES_PER_ROOM} photos.")
        if existing_360 + panos > MAX_PANORAMAS:
            raise forms.ValidationError(f"A room can have at most {MAX_PANORAMAS} 360° photos.")
        lat, lng = cleaned.get("latitude"), cleaned.get("longitude")
        if (lat is None) != (lng is None):
            raise forms.ValidationError("Pick a point on the map (or clear it) - location needs both values.")
        return cleaned

    def save_images(self, service):
        from .models import ServiceImage
        data = self.cleaned_data
        for f in data.get("images") or []:
            ServiceImage.objects.create(service=service, image=f)
        for url in data.get("image_urls") or []:
            ServiceImage.objects.create(service=service, image_url=url)
        for f in data.get("panoramas") or []:
            ServiceImage.objects.create(service=service, image=f, is_360=True)
        for url in data.get("panorama_urls") or []:
            ServiceImage.objects.create(service=service, image_url=url, is_360=True)


class SlotForm(forms.ModelForm):
    class Meta:
        model = Slot
        fields = ["date", "start_time", "end_time"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def __init__(self, *args, service=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.service = service

    def clean(self):
        cleaned = super().clean()
        date, start, end = cleaned.get("date"), cleaned.get("start_time"), cleaned.get("end_time")
        if date and start and end:
            if end <= start:
                raise forms.ValidationError("End time must be after start time.")
            if timezone.make_aware(datetime.datetime.combine(date, start)) <= timezone.now():
                raise forms.ValidationError("That slot is in the past.")
            if self.service and Slot.objects.filter(service=self.service, date=date, start_time=start).exists():
                raise forms.ValidationError("You already have a slot starting at that time.")
        return cleaned


class BulkSlotForm(forms.Form):

    MAX_DAYS = 31
    LENGTHS = [(30, "30 minutes"), (45, "45 minutes"), (60, "1 hour")]

    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    window_start = forms.TimeField(label="Daily from", widget=forms.TimeInput(attrs={"type": "time"}))
    window_end = forms.TimeField(label="Daily until", widget=forms.TimeInput(attrs={"type": "time"}))
    slot_minutes = forms.TypedChoiceField(choices=LENGTHS, coerce=int, label="Each visit lasts")

    def clean(self):
        cleaned = super().clean()
        sd, ed = cleaned.get("start_date"), cleaned.get("end_date")
        ws, we = cleaned.get("window_start"), cleaned.get("window_end")
        minutes = cleaned.get("slot_minutes")
        if sd and ed:
            if ed < sd:
                raise forms.ValidationError("End date must be on or after the start date.")
            if (ed - sd).days + 1 > self.MAX_DAYS:
                raise forms.ValidationError(f"Add at most {self.MAX_DAYS} days at a time.")
            if ed < timezone.localdate():
                raise forms.ValidationError("Those dates are in the past.")
        if ws and we and minutes:
            span = (datetime.datetime.combine(datetime.date.today(), we)
                    - datetime.datetime.combine(datetime.date.today(), ws))
            if span < datetime.timedelta(minutes=minutes):
                raise forms.ValidationError("The daily window is shorter than one visit.")
        return cleaned

    def iter_slots(self):
        c = self.cleaned_data
        step = datetime.timedelta(minutes=c["slot_minutes"])
        now = timezone.now()
        day = c["start_date"]
        while day <= c["end_date"]:
            cursor = datetime.datetime.combine(day, c["window_start"])
            limit = datetime.datetime.combine(day, c["window_end"])
            while cursor + step <= limit:
                if timezone.make_aware(cursor) > now:
                    yield day, cursor.time(), (cursor + step).time()
                cursor += step
            day += datetime.timedelta(days=1)


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ["rating", "comment"]
        widgets = {
            "rating": forms.RadioSelect(choices=[(i, i) for i in range(5, 0, -1)]),
            "comment": forms.Textarea(attrs={"rows": 3, "placeholder": "Share how it went (optional)"}),
        }


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ["reason", "details"]
        widgets = {"details": forms.Textarea(attrs={"rows": 3, "placeholder": "Tell us more (optional)"})}
