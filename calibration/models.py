import os
import secrets
import uuid

from dateutil.relativedelta import relativedelta
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


def new_ics_token():
    return secrets.token_urlsafe(32)


class User(AbstractUser):
    ROLE_OWNER = "owner"
    ROLE_VIEWER_ALL = "viewer_all"
    ROLE_EDITOR_ALL = "editor_all"
    ROLE_ADMIN = "admin"
    ROLE_CHOICES = [
        (ROLE_OWNER, "Owner (edit own devices)"),
        (ROLE_VIEWER_ALL, "Viewer (read all, edit own)"),
        (ROLE_EDITOR_ALL, "Editor (edit all devices)"),
        (ROLE_ADMIN, "Administrator"),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_OWNER)
    email_notifications = models.BooleanField(
        default=True, help_text="Receive calibration reminder emails."
    )
    ics_token = models.CharField(max_length=64, unique=True, default=new_ics_token)

    class Meta:
        ordering = ["last_name", "first_name", "username"]

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def is_app_admin(self):
        return self.is_superuser or self.role == self.ROLE_ADMIN

    @property
    def can_edit_all(self):
        return self.is_app_admin or self.role == self.ROLE_EDITOR_ALL

    @property
    def can_view_all(self):
        return self.can_edit_all or self.role == self.ROLE_VIEWER_ALL

    @property
    def receives_all_reminders(self):
        return self.can_edit_all


def parse_day_list(value):
    days = set()
    for part in (value or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit():
            raise ValidationError(f"'{part}' is not a whole number of days.")
        days.add(int(part))
    return sorted(days, reverse=True)


def validate_day_list(value):
    parse_day_list(value)


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    default_interval_months = models.PositiveIntegerField(
        default=12, help_text="Default calibration interval in months."
    )
    reminder_days = models.CharField(
        max_length=100,
        default="30,7,0",
        validators=[validate_day_list],
        help_text="Days before the due date when reminders are sent, comma separated (e.g. 60,14,0).",
    )

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name

    @property
    def reminder_days_list(self):
        return parse_day_list(self.reminder_days)


class FieldDefinition(models.Model):
    TEXT = "text"
    LONGTEXT = "longtext"
    NUMBER = "number"
    DROPDOWN = "dropdown"
    DATE = "date"
    CHECKBOX = "checkbox"
    FILE = "file"
    TYPE_CHOICES = [
        (TEXT, "Text"),
        (LONGTEXT, "Long text"),
        (NUMBER, "Number"),
        (DROPDOWN, "Dropdown"),
        (DATE, "Date"),
        (CHECKBOX, "Checkbox"),
        (FILE, "File"),
    ]

    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="fields")
    name = models.CharField(max_length=100)
    field_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TEXT)
    required = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    help_text = models.CharField(max_length=255, blank=True)
    options = models.TextField(blank=True, help_text="Dropdown only: one option per line.")
    show_in_list = models.BooleanField(
        default=False, help_text="Show as a column in the device list when filtered by this category."
    )

    class Meta:
        ordering = ["category", "order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["category", "name"], name="unique_field_name_per_category")
        ]

    def __str__(self):
        return f"{self.category}: {self.name}"

    @property
    def options_list(self):
        return [o.strip() for o in self.options.splitlines() if o.strip()]

    def clean(self):
        if self.field_type == self.DROPDOWN and not self.options_list:
            raise ValidationError({"options": "A dropdown needs at least one option."})


class Manufacturer(models.Model):
    name = models.CharField(max_length=100)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(Lower("name"), name="unique_manufacturer_name_ci")]

    def __str__(self):
        return self.name


class DeviceModel(models.Model):
    manufacturer = models.ForeignKey(Manufacturer, on_delete=models.PROTECT, related_name="models")
    name = models.CharField(max_length=100)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["manufacturer__name", "name"]
        verbose_name = "model"
        constraints = [
            models.UniqueConstraint(models.F("manufacturer"), Lower("name"), name="unique_model_name_per_manufacturer_ci")
        ]

    def __str__(self):
        return self.name


class Device(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_AT_CALIBRATION = "at_calibration"
    STATUS_OUT_OF_SERVICE = "out_of_service"
    STATUS_RETIRED = "retired"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_AT_CALIBRATION, "At calibration"),
        (STATUS_OUT_OF_SERVICE, "Out of service"),
        (STATUS_RETIRED, "Retired"),
    ]
    REMINDER_STATUSES = (STATUS_ACTIVE, STATUS_AT_CALIBRATION)

    asset_tag = models.CharField("Asset ID", max_length=50, unique=True)
    name = models.CharField(max_length=200)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="devices")
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="devices")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    manufacturer = models.ForeignKey(
        Manufacturer, on_delete=models.PROTECT, null=True, blank=True, related_name="devices"
    )
    device_model = models.ForeignKey(
        DeviceModel, on_delete=models.PROTECT, null=True, blank=True, related_name="devices", verbose_name="model"
    )
    serial_number = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=100, blank=True)
    interval_override_months = models.PositiveIntegerField(
        "Interval override (months)",
        null=True,
        blank=True,
        help_text="Leave empty to use the category's default interval.",
    )
    last_calibration_date = models.DateField(null=True, blank=True, editable=False)
    next_calibration_date = models.DateField(null=True, blank=True, editable=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["next_calibration_date", "asset_tag"]

    def __str__(self):
        return f"{self.asset_tag} – {self.name}"

    def clean(self):
        if self.device_model_id:
            if not self.manufacturer_id:
                self.manufacturer_id = self.device_model.manufacturer_id
            elif self.device_model.manufacturer_id != self.manufacturer_id:
                raise ValidationError({"device_model": "This model belongs to a different manufacturer."})

    @property
    def effective_interval_months(self):
        if self.interval_override_months:
            return self.interval_override_months
        return self.category.default_interval_months

    def compute_next_date(self):
        if not self.last_calibration_date:
            return None
        return self.last_calibration_date + relativedelta(months=self.effective_interval_months)

    def refresh_calibration_dates(self, save=True):
        """Recompute last/next dates from the calibration history."""
        latest = self.events.order_by("-date").values_list("date", flat=True).first()
        self.last_calibration_date = latest
        self.next_calibration_date = self.compute_next_date()
        if save:
            self.save(update_fields=["last_calibration_date", "next_calibration_date", "updated_at"])

    def days_until_due(self, today=None):
        if not self.next_calibration_date:
            return None
        return (self.next_calibration_date - (today or timezone.localdate())).days

    def due_state(self, today=None, soon_days=30):
        if self.status in (self.STATUS_RETIRED, self.STATUS_OUT_OF_SERVICE):
            return "inactive"
        days = self.days_until_due(today)
        if days is None:
            return "unknown"
        if days < 0:
            return "overdue"
        if days <= soon_days:
            return "due_soon"
        return "ok"

    def custom_values(self):
        """(FieldDefinition, DeviceFieldValue|None) pairs for the device's current category."""
        values = {v.field_id: v for v in self.field_values.all()}
        return [(f, values.get(f.id)) for f in self.category.fields.all()]


def field_file_path(instance, filename):
    return f"fields/{instance.device_id}/{uuid.uuid4().hex}_{os.path.basename(filename)}"


class DeviceFieldValue(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="field_values")
    field = models.ForeignKey(FieldDefinition, on_delete=models.CASCADE, related_name="values")
    value_text = models.TextField(blank=True)
    value_number = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    value_date = models.DateField(null=True, blank=True)
    value_bool = models.BooleanField(null=True)
    value_file = models.FileField(upload_to=field_file_path, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["device", "field"], name="unique_value_per_device_field")
        ]

    def __str__(self):
        return f"{self.device.asset_tag}/{self.field.name}"

    @property
    def value(self):
        t = self.field.field_type
        if t == FieldDefinition.NUMBER:
            return self.value_number
        if t == FieldDefinition.DATE:
            return self.value_date
        if t == FieldDefinition.CHECKBOX:
            return self.value_bool
        if t == FieldDefinition.FILE:
            return self.value_file or None
        return self.value_text

    def display(self):
        v = self.value
        if v is None or v == "":
            return ""
        t = self.field.field_type
        if t == FieldDefinition.NUMBER:
            return format(v.normalize(), "f")
        if t == FieldDefinition.DATE:
            return v.strftime("%d.%m.%Y")
        if t == FieldDefinition.CHECKBOX:
            return "Yes" if v else "No"
        if t == FieldDefinition.FILE:
            return os.path.basename(v.name).split("_", 1)[-1]
        return v


class CalibrationEvent(models.Model):
    RESULT_PASS = "pass"
    RESULT_ADJUSTED = "adjusted"
    RESULT_FAIL = "fail"
    RESULT_LIMITED = "limited"
    RESULT_NOT_RECORDED = "not_recorded"
    RESULT_CHOICES = [
        (RESULT_PASS, "Pass"),
        (RESULT_ADJUSTED, "Pass after adjustment"),
        (RESULT_LIMITED, "Limited use"),
        (RESULT_FAIL, "Fail"),
        (RESULT_NOT_RECORDED, "Not recorded"),
    ]
    PROVIDER_INTERNAL = "internal"
    PROVIDER_EXTERNAL = "external"
    PROVIDER_CHOICES = [(PROVIDER_INTERNAL, "Internal"), (PROVIDER_EXTERNAL, "External lab")]

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="events")
    date = models.DateField("Calibration date")
    provider_type = models.CharField(
        "Performed", max_length=20, choices=PROVIDER_CHOICES, default=PROVIDER_INTERNAL
    )
    performed_by = models.CharField(max_length=200, blank=True, help_text="Person or laboratory.")
    result = models.CharField(max_length=20, choices=RESULT_CHOICES, default=RESULT_PASS)
    certificate_no = models.CharField("Certificate number", max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.device.asset_tag} calibrated {self.date:%d.%m.%Y}"


def attachment_path(instance, filename):
    return f"attachments/{instance.device_id}/{uuid.uuid4().hex}_{os.path.basename(filename)}"


class Attachment(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="attachments")
    event = models.ForeignKey(
        CalibrationEvent, on_delete=models.CASCADE, null=True, blank=True, related_name="attachments"
    )
    file = models.FileField(upload_to=attachment_path)
    original_name = models.CharField(max_length=255)
    description = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.original_name


class AuditLog(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    username = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=50)
    object_type = models.CharField(max_length=50)
    object_id = models.CharField(max_length=50, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)
    device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit")
    changes = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-timestamp", "-id"]

    def __str__(self):
        return f"{self.timestamp:%d.%m.%Y %H:%M} {self.username} {self.action} {self.object_repr}"


class NotificationLog(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="notifications")
    recipient = models.EmailField()
    kind = models.CharField(max_length=30)
    due_date = models.DateField()
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["device", "recipient", "kind", "due_date"], name="unique_notification"
            )
        ]


class SiteSettings(models.Model):
    site_name = models.CharField(max_length=100, default="Calibrator")
    base_url = models.URLField(
        blank=True, help_text="Public address of the app, e.g. https://calibrator.example.com (used in emails and calendar links)."
    )
    notifications_enabled = models.BooleanField(default=True)
    due_soon_days = models.PositiveIntegerField(
        default=30, help_text="Devices due within this many days are shown as 'due soon'."
    )
    overdue_repeat_days = models.PositiveIntegerField(
        default=7, help_text="Repeat overdue reminders every N days."
    )
    smtp_host = models.CharField(max_length=200, blank=True)
    smtp_port = models.PositiveIntegerField(default=587)
    smtp_username = models.CharField(max_length=200, blank=True)
    smtp_password = models.CharField(max_length=200, blank=True)
    smtp_security = models.CharField(
        max_length=10,
        choices=[("starttls", "STARTTLS (port 587)"), ("ssl", "SSL/TLS (port 465)"), ("none", "None")],
        default="starttls",
    )
    from_email = models.EmailField(blank=True)

    class Meta:
        verbose_name_plural = "site settings"

    def __str__(self):
        return "Site settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def smtp_configured(self):
        return bool(self.smtp_host and self.from_email)
