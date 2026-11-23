from django import forms
from django.contrib import messages
from django.shortcuts import redirect, render

from .models import ContactMessage

FAQS = [
    ("Is RoomSaathi really broker-free?", "Yes. Owners list their own rooms and you deal with them directly. We never charge a brokerage on the rent."),
    ("What is a visit slot?", "A time window when the owner is free to show you the room in person. You book one with a small refundable token and go see the room before you decide."),
    ("How does booking a room work?", "Send a request with your move-in date and stay length. The owner approves or declines within 48 hours. If approved, pay the advance online within 24 hours and the room is yours. Deposit and rent are paid to the owner at move-in."),
    ("When do I get my advance back?", "Cancel at least 3 days before your move-in date for a full refund. If the owner cancels, you are always refunded in full."),
    ("Why do I need to verify my phone?", "A one-time OTP keeps fake accounts out so tenants and owners can trust each other. It takes under a minute."),
    ("What does the Verified owner badge mean?", "Our team has spoken to the owner and confirmed they own or manage the property."),
    ("Is my payment safe?", "Payments are processed by Razorpay. We never see or store your card or UPI details."),
    ("I'm an owner. What does it cost to list?", "Listing is free. You choose your own visit token and advance amounts."),
]


def about(request):
    return render(request, "pages/about.html")


def faq(request):
    return render(request, "pages/faq.html", {"faqs": FAQS})


def terms(request):
    return render(request, "pages/terms.html")


def privacy(request):
    return render(request, "pages/privacy.html")


class ContactForm(forms.ModelForm):
    website = forms.CharField(required=False)

    class Meta:
        model = ContactMessage
        fields = ["name", "email", "message"]
        widgets = {"message": forms.Textarea(attrs={"rows": 5, "maxlength": 2000})}


def contact(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            if not form.cleaned_data["website"]:
                ContactMessage.objects.create(**{k: form.cleaned_data[k] for k in ("name", "email", "message")})
            messages.success(request, "Thanks! We've got your message and will reply by email.")
            return redirect("pages:contact")
    else:
        initial = {}
        if request.user.is_authenticated:
            initial = {"name": request.user.get_full_name() or request.user.username, "email": request.user.email}
        form = ContactForm(initial=initial)
    return render(request, "pages/contact.html", {"form": form})
