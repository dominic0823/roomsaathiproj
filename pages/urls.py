from django.urls import path
from . import views

app_name = "pages"

urlpatterns = [
    path("about/", views.about, name="about"),
    path("help/", views.faq, name="faq"),
    path("terms/", views.terms, name="terms"),
    path("privacy/", views.privacy, name="privacy"),
    path("contact/", views.contact, name="contact"),
]
