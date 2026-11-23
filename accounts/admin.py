from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Notification, OTPCode, User


@admin.action(description="Mark selected owners as verified")
def mark_verified(modeladmin, request, queryset):
    queryset.update(is_verified=True, verification_requested=False)


@admin.action(description="Remove verified badge")
def remove_verified(modeladmin, request, queryset):
    queryset.update(is_verified=False)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "role", "phone_verified", "is_verified", "verification_requested", "is_staff")
    list_filter = UserAdmin.list_filter + ("role", "phone_verified", "is_verified", "verification_requested")
    search_fields = UserAdmin.search_fields + ("phone_number",)
    actions = [mark_verified, remove_verified]
    fieldsets = UserAdmin.fieldsets + (
        ("Marketplace Info", {"fields": (
            "role", "phone_number", "phone_verified", "email_verified", "avatar",
            "is_verified", "verification_requested", "verification_note",
        )}),
    )


@admin.register(OTPCode)
class OTPCodeAdmin(admin.ModelAdmin):
    list_display = ("user", "channel", "purpose", "target", "attempts", "created_at", "used_at")
    list_filter = ("channel", "purpose")
    readonly_fields = [f.name for f in OTPCode._meta.fields]


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "message", "is_read", "created_at")
