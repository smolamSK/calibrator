from .models import SiteSettings


def theme(request):
    """Color mode and accent: the user's choice, else the site default."""
    site = SiteSettings.load()
    user = getattr(request, "user", None)
    personal = user if user is not None and user.is_authenticated else None
    return {
        "theme_choices": [("light", "☀", "Light"), ("dark", "☾", "Dark"), ("auto", "◐", "Auto (follow system)")],
        "theme_mode": (personal and personal.theme_mode) or site.theme_mode,
        "theme_accent": (personal and personal.theme_accent) or site.theme_accent,
    }
