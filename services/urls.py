from django.urls import path
from . import views

app_name = "services"

urlpatterns = [
    path("", views.service_list, name="list"),
    path("dashboard/", views.provider_dashboard, name="provider_dashboard"),
    path("create/", views.create_service, name="create"),
    path("favorites/", views.my_favorites, name="my_favorites"),
    path("compare/", views.compare_view, name="compare"),
    path("compare/clear/", views.compare_clear, name="compare_clear"),
    path("compare/<int:pk>/", views.compare_toggle, name="compare_toggle"),
    path("alerts/", views.saved_searches, name="saved_searches"),
    path("alerts/save/", views.save_search, name="save_search"),
    path("alerts/<int:pk>/delete/", views.delete_search, name="delete_search"),
    path("owner/<str:username>/", views.owner_profile, name="owner_profile"),
    path("<int:pk>/", views.service_detail, name="detail"),
    path("<int:pk>/edit/", views.edit_service, name="edit"),
    path("<int:pk>/pause/", views.toggle_active, name="toggle_active"),
    path("<int:pk>/delete/", views.delete_service, name="delete"),
    path("<int:pk>/report/", views.report_service, name="report"),
    path("<int:pk>/slots/", views.manage_slots, name="manage_slots"),
    path("<int:pk>/slots/<int:slot_id>/delete/", views.delete_slot, name="delete_slot"),
    path("<int:pk>/favorite/", views.toggle_favorite, name="toggle_favorite"),
]
