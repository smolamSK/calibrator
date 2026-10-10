import logging
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from django.core.mail import EmailMessage, get_connection
from django.db import IntegrityError, transaction
from django.db.models import Model
from django.db.models.fields.files import FieldFile
from django.urls import reverse
from django.utils import timezone

from .models import AuditLog, Device, NotificationLog, SiteSettings, User

log = logging.getLogger(__name__)


# ---------------------------------------------------------------- audit log


def _plain(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, Model):
        return str(value)
    if isinstance(value, FieldFile):
        return value.name or None
    if hasattr(value, "name") and hasattr(value, "read"):  # uploaded file
        return value.name
    if isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def audit(user, action, obj, changes=None, device=None):
    if device is None and isinstance(obj, Device):
        device = obj
    AuditLog.objects.create(
        user=user if user and user.is_authenticated else None,
        username=getattr(user, "username", "") or "system",
        action=action,
        object_type=obj._meta.verbose_name.title() if isinstance(obj, Model) else str(obj),
        object_id=str(getattr(obj, "pk", "") or ""),
        object_repr=str(obj)[:255],
        device=device,
        changes={k: [_plain(a), _plain(b)] for k, (a, b) in (changes or {}).items()},
    )


def form_changes(form, old_values):
    """{label: (old, new)} for the fields a bound form changed, given values captured before saving."""
    changes = {}
    for name in form.changed_data:
        label = str(form.fields[name].label or name)
        new = form.cleaned_data.get(name)
        old = old_values.get(name)
        if _plain(old) != _plain(new):
            changes[label] = (old, new)
    return changes


def snapshot(instance, field_names):
    return {name: getattr(instance, name, None) for name in field_names}


# -------------------------------------------------------- calibration dates


@transaction.atomic
def save_calibration_event(event, user, created):
    event.save()
    device = event.device
    before = device.next_calibration_date
    device.refresh_calibration_dates()
    if created:
        audit(user, "calibration added", event, device=device, changes={
            "Date": (None, event.date),
            "Result": (None, event.get_result_display()),
            "Certificate": (None, event.certificate_no),
            "Next calibration": (before, device.next_calibration_date),
        })
    return device


@transaction.atomic
def delete_calibration_event(event, user):
    device = event.device
    before = device.next_calibration_date
    audit(user, "calibration deleted", event, device=device, changes={
        "Date": (event.date, None),
        "Next calibration": (before, None),
    })
    for att in event.attachments.all():
        att.file.delete(save=False)
    event.delete()
    device.refresh_calibration_dates()


# ---------------------------------------------------------------- reminders


def reminder_kind(device, today, overdue_repeat_days=7):
    """Return the reminder kind due today for this device, or None.

    Before the due date the most urgent passed lead-day threshold is used
    (e.g. 'lead-14'); after it, 'overdue-N' where N increments every
    `overdue_repeat_days`. Each kind is sent once per due date, so a missed
    run catches up without duplicating.
    """
    if device.status not in Device.REMINDER_STATUSES or not device.next_calibration_date:
        return None
    days_left = (device.next_calibration_date - today).days
    if days_left < 0:
        step = max(1, overdue_repeat_days)
        return f"overdue-{(-days_left - 1) // step}"
    passed = [d for d in device.effective_reminder_days_list if days_left <= d]
    if not passed:
        return None
    return f"lead-{min(passed)}"


def all_reminder_recipients():
    return [
        u for u in User.objects.filter(is_active=True, email_notifications=True).exclude(email="")
        if u.receives_all_reminders
    ]


def collect_reminders(today=None):
    """{recipient_email: [(device, kind), ...]} for reminders not sent yet."""
    today = today or timezone.localdate()
    settings = SiteSettings.load()
    watchers = all_reminder_recipients()
    pending = defaultdict(list)
    devices = Device.objects.filter(
        status__in=Device.REMINDER_STATUSES, next_calibration_date__isnull=False
    ).select_related("owner", "manufacturer", "device_model")
    for device in devices:
        kind = reminder_kind(device, today, settings.overdue_repeat_days)
        if not kind:
            continue
        recipients = {u.email.lower() for u in watchers}
        owner = device.owner
        if owner.is_active and owner.email and owner.email_notifications:
            recipients.add(owner.email.lower())
        already = set(
            NotificationLog.objects.filter(
                device=device, kind=kind, due_date=device.next_calibration_date
            ).values_list("recipient", flat=True)
        )
        for email in sorted(recipients - already):
            pending[email].append((device, kind))
    return pending


def _kind_label(kind, device, today):
    days = (device.next_calibration_date - today).days
    if kind.startswith("overdue"):
        return f"OVERDUE by {-days} day(s)"
    if days == 0:
        return "due TODAY"
    return f"due in {days} day(s)"


def build_reminder_email(email, items, today, settings):
    items = sorted(items, key=lambda i: i[0].next_calibration_date)
    overdue = sum(1 for _, k in items if k.startswith("overdue"))
    subject = f"[{settings.site_name}] {len(items)} device(s) need calibration"
    if overdue:
        subject += f" ({overdue} overdue)"
    base = settings.base_url.rstrip("/")
    lines = ["The following devices need calibration:", ""]
    for device, kind in items:
        make = " ".join(str(x) for x in (device.manufacturer, device.device_model) if x)
        lines.append(
            f"- {device.asset_tag} {device.name}{f' ({make})' if make else ''} — "
            f"{_kind_label(kind, device, today)}, due {device.next_calibration_date:%d.%m.%Y}, "
            f"owner {device.owner}"
        )
        if base:
            lines.append(f"  {base}{reverse('device_detail', args=[device.pk])}")
    lines += ["", "You receive this because you own the device or manage all devices.",
              "Notification settings can be changed in your profile."]
    return EmailMessage(subject, "\n".join(lines), settings.from_email or None, [email])


def send_reminders(today=None, dry_run=False):
    """Send pending reminders, one email per recipient. Returns list of (email, n_devices)."""
    today = today or timezone.localdate()
    settings = SiteSettings.load()
    if not settings.notifications_enabled:
        log.info("Notifications disabled in settings")
        return []
    pending = collect_reminders(today)
    if not pending:
        return []
    if not dry_run and not settings.smtp_configured:
        log.warning("SMTP not configured; %d reminder email(s) not sent", len(pending))
        return []
    sent = []
    connection = None if dry_run else get_connection()
    for email, items in pending.items():
        msg = build_reminder_email(email, items, today, settings)
        if dry_run:
            print(f"--- To: {email}\nSubject: {msg.subject}\n{msg.body}\n")
            sent.append((email, len(items)))
            continue
        try:
            msg.connection = connection
            msg.send()
        except Exception:
            log.exception("Failed to send reminder to %s", email)
            continue
        for device, kind in items:
            try:
                NotificationLog.objects.create(
                    device=device, recipient=email, kind=kind, due_date=device.next_calibration_date
                )
            except IntegrityError:
                pass
        sent.append((email, len(items)))
    return sent
