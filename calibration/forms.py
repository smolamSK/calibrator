from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import (
    Attachment,
    CalibrationEvent,
    Device,
    DeviceFieldValue,
    DeviceModel,
    FieldDefinition,
    Manufacturer,
    SiteSettings,
    User,
)

MAX_UPLOAD_MB = 25


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, attrs=None):
        super().__init__(attrs=attrs, format="%Y-%m-%d")


class BootstrapMixin:
    def apply_bootstrap(self):
        for field in self.fields.values():
            w = field.widget
            if isinstance(w, (forms.CheckboxInput,)):
                css = "form-check-input"
            elif isinstance(w, (forms.Select, forms.SelectMultiple)):
                css = "form-select"
            else:
                css = "form-control"
            w.attrs["class"] = (w.attrs.get("class", "") + " " + css).strip()


def check_upload_size(f):
    if f and hasattr(f, "size") and f.size > MAX_UPLOAD_MB * 1024 * 1024:
        raise forms.ValidationError(f"File is larger than {MAX_UPLOAD_MB} MB.")
    return f


# ------------------------------------------------------------ device forms


class ModelSelect(forms.Select):
    """Model dropdown whose options carry their manufacturer id, so JS can filter by brand."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, "instance", None)
        if instance is not None:
            option["attrs"]["data-manufacturer"] = instance.manufacturer_id
        return option


def custom_field_name(fd):
    return f"cf_{fd.id}"


def build_custom_field(fd, existing=None):
    common = {"label": fd.name, "help_text": fd.help_text, "required": fd.required}
    t = fd.field_type
    if t == FieldDefinition.TEXT:
        return forms.CharField(max_length=500, **common)
    if t == FieldDefinition.LONGTEXT:
        return forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), **common)
    if t == FieldDefinition.NUMBER:
        return forms.DecimalField(max_digits=20, decimal_places=6, **common)
    if t == FieldDefinition.DROPDOWN:
        options = fd.options_list
        current = existing.value_text if existing else ""
        if current and current not in options:
            options = options + [current]
        return forms.ChoiceField(choices=[("", "---------")] + [(o, o) for o in options], **common)
    if t == FieldDefinition.DATE:
        return forms.DateField(widget=DateInput, **common)
    if t == FieldDefinition.CHECKBOX:
        common["required"] = False
        return forms.BooleanField(**common)
    if t == FieldDefinition.FILE:
        has_file = bool(existing and existing.value_file)
        common["required"] = fd.required and not has_file
        return forms.FileField(widget=forms.FileInput, validators=[check_upload_size], **common)
    raise ValueError(f"Unknown field type {t}")


class DeviceForm(BootstrapMixin, forms.ModelForm):
    initial_calibration_date = forms.DateField(
        required=False,
        widget=DateInput,
        label="Last calibration date",
        help_text="Optional: date of the most recent calibration (creates the first history entry).",
    )

    class Meta:
        model = Device
        fields = [
            "asset_tag", "name", "owner", "status", "manufacturer", "device_model",
            "serial_number", "location", "interval_override_months", "notes",
        ]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3}), "device_model": ModelSelect}

    def __init__(self, *args, user, manufacturer=None, device_model=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["owner"].queryset = User.objects.filter(is_active=True)
        if not user.can_edit_all:
            del self.fields["owner"]
        if self.instance.pk:
            del self.fields["initial_calibration_date"]
        for name in ("manufacturer", "device_model"):
            self.fields[name].widget.attrs["data-reload"] = "1"
        self.fields["manufacturer"].widget.attrs["data-lookup"] = "manufacturer"
        self.fields["device_model"].widget.attrs["data-lookup"] = "model"
        self.fields["device_model"].queryset = DeviceModel.objects.select_related("manufacturer")

        if manufacturer is None and device_model is None and self.instance.pk:
            manufacturer, device_model = self.instance.manufacturer, self.instance.device_model
        if device_model and manufacturer and device_model.manufacturer_id != manufacturer.pk:
            device_model = None
        self.field_owners = [o for o in (manufacturer, device_model) if o]
        self.custom_fields = []
        if self.field_owners:
            existing = {}
            if self.instance.pk:
                existing = {v.field_id: v for v in self.instance.field_values.all()}
            for fd in [fd for owner in self.field_owners for fd in owner.fields.all()]:
                name = custom_field_name(fd)
                value = existing.get(fd.id)
                self.fields[name] = build_custom_field(fd, value)
                if value is not None and fd.field_type != FieldDefinition.FILE:
                    self.initial.setdefault(name, value.value)
                if fd.field_type == FieldDefinition.FILE and value and value.value_file and not fd.required:
                    self.fields[name + "_clear"] = forms.BooleanField(required=False, label="Remove file")
                self.custom_fields.append((fd, name, value))
        self.apply_bootstrap()

    def standard_fields(self):
        names = [n for n in self.fields if not n.startswith("cf_")]
        return [self[n] for n in names]

    def custom_bound_fields(self):
        return [
            (fd, self[name], value, self[name + "_clear"] if name + "_clear" in self.fields else None)
            for fd, name, value in self.custom_fields
        ]

    def custom_snapshot(self):
        return {fd.name: (value.display() if value else "") for fd, _, value in self.custom_fields}

    def save_custom_values(self, device):
        """Persist dynamic field values; returns {label: (old, new)} changes."""
        changes = {}
        for fd, name, value in self.custom_fields:
            if name not in self.cleaned_data:
                continue
            new = self.cleaned_data[name]
            obj = value or DeviceFieldValue(device=device, field=fd)
            old_display = obj.display() if obj.pk else ""
            t = fd.field_type
            if t == FieldDefinition.FILE:
                if self.cleaned_data.get(name + "_clear") and not new:
                    if obj.value_file:
                        obj.value_file.delete(save=False)
                    obj.value_file = ""
                elif new:
                    if obj.value_file:
                        obj.value_file.delete(save=False)
                    obj.value_file = new
                else:
                    continue
            elif t == FieldDefinition.NUMBER:
                obj.value_number = new
            elif t == FieldDefinition.DATE:
                obj.value_date = new
            elif t == FieldDefinition.CHECKBOX:
                obj.value_bool = bool(new)
            else:
                obj.value_text = new or ""
            obj.save()
            new_display = obj.display()
            if old_display != new_display:
                changes[fd.name] = (old_display, new_display)
        return changes


class DeviceFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Search")
    status = forms.ChoiceField(
        required=False, choices=[("", "Any status"), ("in_use", "In use (not retired)")] + Device.STATUS_CHOICES
    )
    due = forms.ChoiceField(
        required=False,
        choices=[("", "Any due date"), ("overdue", "Overdue"), ("due_soon", "Due soon"),
                 ("ok", "OK"), ("unknown", "Never calibrated")],
    )
    manufacturer = forms.ModelChoiceField(Manufacturer.objects.all(), required=False, empty_label="All brands")
    device_model = forms.ModelChoiceField(
        DeviceModel.objects.select_related("manufacturer"), required=False, empty_label="All models", widget=ModelSelect
    )
    owner = forms.ModelChoiceField(User.objects.filter(is_active=True), required=False, empty_label="All owners")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None and not user.can_view_all:
            del self.fields["owner"]
        for f in self.fields.values():
            css = "form-select form-select-sm" if isinstance(f.widget, forms.Select) else "form-control form-control-sm"
            f.widget.attrs["class"] = css
        self.fields["q"].widget.attrs["placeholder"] = "Asset ID, name, serial, location…"
        self.fields["manufacturer"].widget.attrs["data-lookup"] = "manufacturer"
        self.fields["device_model"].widget.attrs["data-lookup"] = "model"


# -------------------------------------------------------- brands & models


class LookupNameMixin:
    """Case-insensitive duplicate check for brand/model names."""

    def duplicates(self, name):
        raise NotImplementedError

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if self.duplicates(name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(f"“{name}” already exists.")
        return name


class ManufacturerForm(LookupNameMixin, BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Manufacturer
        fields = ["name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()

    def duplicates(self, name):
        return Manufacturer.objects.filter(name__iexact=name)


class ManufacturerEditForm(ManufacturerForm):
    class Meta(ManufacturerForm.Meta):
        fields = ["name", "interval_months", "reminder_days"]


class DeviceModelForm(LookupNameMixin, BootstrapMixin, forms.ModelForm):
    class Meta:
        model = DeviceModel
        fields = ["manufacturer", "name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()

    def duplicates(self, name):
        brand = self.cleaned_data.get("manufacturer")
        return DeviceModel.objects.filter(manufacturer=brand, name__iexact=name)


class DeviceModelEditForm(DeviceModelForm):
    class Meta(DeviceModelForm.Meta):
        fields = ["manufacturer", "name", "interval_months", "reminder_days"]


# ------------------------------------------------------- calibration events


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [check_upload_size(single(d, initial)) for d in data if d]
        return [check_upload_size(single(data, initial))] if data else []


class CalibrationEventForm(BootstrapMixin, forms.ModelForm):
    files = MultipleFileField(
        required=False, label="Certificate / attachments", help_text="PDF, images… (multiple allowed)"
    )

    class Meta:
        model = CalibrationEvent
        fields = ["date", "provider_type", "performed_by", "result", "certificate_no", "notes"]
        widgets = {"date": DateInput, "notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()


class AttachmentForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Attachment
        fields = ["file", "description"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["file"].validators.append(check_upload_size)
        self.apply_bootstrap()


# ------------------------------------------------------------ admin forms


class FieldDefinitionForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = FieldDefinition
        fields = ["name", "field_type", "required", "show_in_list", "order", "help_text", "options"]
        widgets = {"options": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.values.exists():
            self.fields["field_type"].disabled = True
            self.fields["field_type"].help_text = "Type cannot be changed once devices have values for this field."
        self.apply_bootstrap()

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        fd = self.instance
        siblings = FieldDefinition.objects.filter(manufacturer=fd.manufacturer, device_model=fd.device_model)
        if siblings.filter(name__iexact=name).exclude(pk=fd.pk).exists():
            raise forms.ValidationError(f"A field named “{name}” already exists here.")
        return name


class UserCreateForm(BootstrapMixin, UserCreationForm):
    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "role", "email_notifications"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        self.apply_bootstrap()


class UserEditForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "role", "email_notifications", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        self.fields["is_active"].help_text = "Inactive users cannot log in and receive no emails."
        self.apply_bootstrap()


class ProfileForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "email_notifications"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        self.apply_bootstrap()


class SiteSettingsForm(BootstrapMixin, forms.ModelForm):
    smtp_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        label="SMTP password",
        help_text="Leave empty to keep the current password.",
    )
    clear_password = forms.BooleanField(required=False, label="Remove stored SMTP password")

    class Meta:
        model = SiteSettings
        fields = [
            "site_name", "base_url", "notifications_enabled", "due_soon_days", "overdue_repeat_days",
            "default_interval_months", "default_reminder_days",
            "smtp_host", "smtp_port", "smtp_security", "smtp_username", "smtp_password", "from_email",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.cleaned_data.get("clear_password"):
            obj.smtp_password = ""
        elif not self.cleaned_data.get("smtp_password"):
            obj.smtp_password = SiteSettings.load().smtp_password
        if commit:
            obj.save()
        return obj


class ImportUploadForm(BootstrapMixin, forms.Form):
    file = forms.FileField(help_text="Excel (.xlsx) or CSV file with a header row.", validators=[check_upload_size])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()

    def clean_file(self):
        f = self.cleaned_data["file"]
        if not f.name.lower().endswith((".xlsx", ".csv")):
            raise forms.ValidationError("Upload a .xlsx or .csv file.")
        return f
