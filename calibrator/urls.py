from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from calibration.email_backend import default_from_email


class PasswordResetView(auth_views.PasswordResetView):
    def form_valid(self, form):
        self.from_email = default_from_email()
        return super().form_valid(form)


urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("accounts/password_reset/", PasswordResetView.as_view(), name="password_reset"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("calibration.urls")),
]
