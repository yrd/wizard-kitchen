"""cookpot Django URL Configuration.

See here for more information:
https://docs.djangoproject.com/en/4.0/topics/http/urls/
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from .ingredients import views as ingredients_views

urlpatterns = [
    path("", ingredients_views.index, name="index"),
    path("data/section_cards", ingredients_views.section_cards, name="section_cards"),
    path("admin/", admin.site.urls),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
