from django import template
from django.utils.html import format_html

register = template.Library()

STATE_BADGES = {
    "overdue": ("danger", "Overdue"),
    "due_soon": ("warning text-dark", "Due soon"),
    "ok": ("success", "OK"),
    "unknown": ("secondary", "Never calibrated"),
    "inactive": ("light text-dark border", "Inactive"),
}

STATUS_BADGES = {
    "active": "success",
    "at_calibration": "info text-dark",
    "out_of_service": "warning text-dark",
    "retired": "secondary",
}


@register.simple_tag
def state_badge(state):
    css, label = STATE_BADGES.get(state, ("secondary", state))
    return format_html('<span class="badge bg-{}">{}</span>', css, label)


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
