from django.contrib import admin
from .models import Amenity, Category, Favorite, Report, Review, Service, ServiceImage, Slot


class SlotInline(admin.TabularInline):
    model = Slot
    extra = 1


class ServiceImageInline(admin.TabularInline):
    model = ServiceImage
    extra = 0


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)


@admin.register(Amenity)
class AmenityAdmin(admin.ModelAdmin):
    list_display = ("icon", "name")


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("title", "provider", "category", "price", "total_beds", "advance_amount", "is_active")
    list_filter = ("category", "is_active", "tenant_preference", "provider__is_verified")
    search_fields = ("title", "location", "provider__username")
    filter_horizontal = ("amenities",)
    inlines = [ServiceImageInline, SlotInline]


@admin.register(Slot)
class SlotAdmin(admin.ModelAdmin):
    list_display = ("service", "date", "start_time", "end_time", "is_booked")
    list_filter = ("is_booked", "date")


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("service", "customer", "rating", "created_at")
    list_filter = ("rating",)


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ("user", "service", "created_at")


@admin.action(description="Mark selected reports as resolved")
def resolve_reports(modeladmin, request, queryset):
    queryset.update(resolved=True)


@admin.action(description="Pause the reported listings (hide from tenants)")
def pause_reported_listings(modeladmin, request, queryset):
    Service.objects.filter(pk__in=queryset.values_list("service_id", flat=True)).update(is_active=False)


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("service", "reason", "reporter", "resolved", "created_at")
    list_filter = ("resolved", "reason")
    actions = [resolve_reports, pause_reported_listings]
