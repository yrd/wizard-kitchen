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
    path("pairing/", ingredients_views.pairing_view),
    path("admin/", admin.site.urls),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
