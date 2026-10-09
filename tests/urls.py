from django.contrib import admin
from django.urls import include, path

from .apps.example.views import index, payment_create, payment_details

urlpatterns = [
    path("", index),
    path("fail", index),
    path("success", index),
    path("payment_create", payment_create),
    path("payment_details/<uuid:payment_id>", payment_details),
    path("payments/", include("payments.urls")),
    path("admin", admin.site.urls),
]
