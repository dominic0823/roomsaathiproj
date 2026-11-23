import datetime

from django import forms
from django.utils import timezone

MAX_MONTHS = 24
MAX_DAYS_AHEAD = 120


class RentalRequestForm(forms.Form):
    move_in_date = forms.DateField()
    stay_months = forms.IntegerField()
    note = forms.CharField(max_length=500, required=False)

    def __init__(self, *args, service, **kwargs):
        super().__init__(*args, **kwargs)
        self.service = service

    def clean_move_in_date(self):
        d = self.cleaned_data["move_in_date"]
        today = timezone.localdate()
        if d < today:
            raise forms.ValidationError("Move-in date can't be in the past.")
        if d > today + datetime.timedelta(days=MAX_DAYS_AHEAD):
            raise forms.ValidationError(f"Move-in must be within {MAX_DAYS_AHEAD} days from today.")
        return d

    def clean_stay_months(self):
        m = self.cleaned_data["stay_months"]
        if m < self.service.min_stay_months:
            raise forms.ValidationError(f"Minimum stay for this room is {self.service.min_stay_months} month(s).")
        if m > MAX_MONTHS:
            raise forms.ValidationError(f"Maximum stay is {MAX_MONTHS} months.")
        return m
