from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .models import Service


class ServiceSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.8

    def items(self):
        return Service.objects.filter(is_active=True).order_by("pk")


class StaticSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.5

    def items(self):
        return ["home", "services:list", "pages:about", "pages:faq", "pages:contact"]

    def location(self, item):
        return reverse(item)
