from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.urls import re_path
from django.views.static import serve
from django.contrib.sitemaps.views import sitemap
from django.http import HttpResponse
from services import views as service_views
from services.sitemaps import ServiceSitemap, StaticSitemap


def robots_txt(request):
    lines = ["User-agent: *", "Disallow: /admin/", "Disallow: /accounts/", "Disallow: /bookings/", "Disallow: /payments/", "Disallow: /chat/",
             f"Sitemap: {request.build_absolute_uri('/sitemap.xml')}"]
    return HttpResponse("\n".join(lines), content_type="text/plain")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", service_views.home, name="home"),
    path("sitemap.xml", sitemap, {"sitemaps": {"rooms": ServiceSitemap, "pages": StaticSitemap}}, name="sitemap"),
    path("robots.txt", robots_txt),
    path("", include("pages.urls")),
    path("accounts/", include("accounts.urls")),
    path("services/", include("services.urls")),
    path("bookings/", include("bookings.urls")),
    path("chat/", include("chatapp.urls")),
    path("payments/", include("payments.urls")),
    path("api/", include("services.api_urls")),
    path("api/", include("bookings.api_urls")),
]

def media_file(request, path):
    return serve(request, path, document_root=settings.MEDIA_ROOT)


if not settings.USE_OBJECT_STORAGE:
    urlpatterns += [re_path(rf"^{settings.MEDIA_URL.lstrip('/')}(?P<path>.*)$", media_file)]
