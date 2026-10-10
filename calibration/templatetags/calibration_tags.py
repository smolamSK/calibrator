from django import template
from django.utils.html import format_html

register = template.Library()

STATE_BADGES = {
    "overdue": ("danger", "Overdue", "exclamation-triangle-fill"),
    "due_soon": ("warning text-dark", "Due soon", "clock"),
    "ok": ("success", "OK", "check-circle"),
    "unknown": ("secondary", "Never calibrated", "question-circle"),
    "inactive": ("body-tertiary text-body border", "Inactive", "pause-circle"),
}

STATUS_BADGES = {
    "active": "success",
    "at_calibration": "info text-dark",
    "out_of_service": "warning text-dark",
    "retired": "secondary",
}


@register.simple_tag
def icon(name, extra=""):
    return format_html('<i class="bi bi-{}{}" aria-hidden="true"></i>', name, f" {extra}" if extra else "")


@register.simple_tag
def state_badge(state):
    css, label, glyph = STATE_BADGES.get(state, ("secondary", state, "circle"))
    return format_html('<span class="badge bg-{}">{} {}</span>', css, icon(glyph), label)


@register.filter
def state_color(state):
    """Bootstrap color name for a due state (card borders, dots)."""
    return {"overdue": "danger", "due_soon": "warning", "ok": "success"}.get(state, "secondary")


@register.simple_tag
def status_badge(device):
    return format_html(
        '<span class="badge bg-{}">{}</span>', STATUS_BADGES.get(device.status, "secondary"), device.get_status_display()
    )


@register.filter
def days_text(days):
    if days is None:
        return ""
    if days < 0:
        return f"{-days} day{'s' if days != -1 else ''} overdue"
    if days == 0:
        return "due today"
    return f"in {days} day{'s' if days != 1 else ''}"


@register.simple_tag
def device_rows(devices):
    """[{device, state, days}] for templates that only have a device list."""
    from django.utils import timezone

    from ..models import SiteSettings

    today, soon = timezone.localdate(), SiteSettings.load().due_soon_days
    return [{"device": d, "state": d.due_state(today, soon), "days": d.days_until_due(today)} for d in devices]
