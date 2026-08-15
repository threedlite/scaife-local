# LOCAL CHANGE (2026-08-14): was `from django.conf.urls import include, url`.
# django.conf.urls.url was removed in Django 4.0; re_path is the direct
# replacement and behaves identically for a regex pattern.
from django.urls import include, re_path


urlpatterns = [re_path(r"^", include("scaife_viewer.core.urls"))]
