from django.core.mail.backends.smtp import EmailBackend


class DatabaseSMTPBackend(EmailBackend):
    """SMTP backend whose connection settings come from SiteSettings (editable in the UI)."""

    def __init__(self, fail_silently=False, **kwargs):
        from .models import SiteSettings

        s = SiteSettings.load()
        super().__init__(
            host=s.smtp_host or "localhost",
            port=s.smtp_port,
            username=s.smtp_username or None,
            password=s.smtp_password or None,
            use_tls=s.smtp_security == "starttls",
            use_ssl=s.smtp_security == "ssl",
            timeout=30,
            fail_silently=fail_silently,
            **kwargs,
        )


def default_from_email():
    from .models import SiteSettings

    s = SiteSettings.load()
    return s.from_email or None
