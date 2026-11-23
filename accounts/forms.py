from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User
from .otp import normalize_phone


def clean_phone(value, required=False):
    normalized = normalize_phone(value)
    if normalized is None:
        raise forms.ValidationError("Enter a valid mobile number, e.g. 98765 43210 or +91 98765 43210.")
    if not normalized and required:
        raise forms.ValidationError("Phone number is required.")
    return normalized


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    role = forms.ChoiceField(choices=User.Role.choices, widget=forms.RadioSelect, label="I am a...")
    phone_number = forms.CharField(max_length=20, label="Mobile number (we'll verify it by OTP)")

    class Meta:
        model = User
        fields = ["username", "email", "phone_number", "role", "password1", "password2"]

    def clean_phone_number(self):
        return clean_phone(self.cleaned_data.get("phone_number"), required=True)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.role = self.cleaned_data["role"]
        user.phone_number = self.cleaned_data["phone_number"]
        if commit:
            user.save()
        return user


class ProfileForm(forms.ModelForm):
    phone_number = forms.CharField(max_length=20, label="Mobile number")
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ["first_name", "email", "phone_number"]
        labels = {"first_name": "Your name"}

    def clean_phone_number(self):
        return clean_phone(self.cleaned_data.get("phone_number"), required=True)


class VerificationRequestForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["verification_note"]
        labels = {"verification_note": "Anything that helps us verify you (optional)"}
        widgets = {
            "verification_note": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": "e.g. I own the property at ..., best time to call is ...",
            })
        }
