from django.contrib import admin
from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "service", "customer", "status", "total_price", "move_in_date", "created_at")
    list_filter = ("kind", "status")
    search_fields = ("service__title", "customer__username")
