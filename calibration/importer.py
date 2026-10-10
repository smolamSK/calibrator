"""Device import from XLSX/CSV: read -> map columns -> validate (preview) -> apply."""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction

from .models import (
    CalibrationEvent,
    Device,
    DeviceFieldValue,
    DeviceModel,
    FieldDefinition,
    Manufacturer,
    User,
)
from .services import audit

MAX_ROWS = 5000

TARGETS = [
    # key, label, required, header aliases
    ("asset_tag", "Asset ID", True, ["asset id", "asset", "asset tag", "id", "inventory number", "inv no", "tag"]),
    ("name", "Name", True, ["name", "device", "device name", "description", "instrument"]),
    ("owner", "Owner (username or email)", True, ["owner", "user", "responsible", "username", "email", "owner email"]),
    ("status", "Status", False, ["status", "state"]),
    ("manufacturer", "Manufacturer", False, ["manufacturer", "make", "brand", "vendor"]),
    ("model", "Model", False, ["model"]),
    ("serial_number", "Serial number", False, ["serial", "serial number", "serial no", "s/n", "sn"]),
    ("location", "Location", False, ["location", "place", "room", "site"]),
    ("interval_override_months", "Interval override (months)", False, ["interval", "interval months", "interval (months)", "calibration interval"]),
    ("last_calibration_date", "Last calibration date", False, ["last calibration", "last calibration date", "calibration date", "last cal", "calibrated"]),
    ("certificate_no", "Certificate number (of last calibration)", False, ["certificate", "certificate no", "certificate number", "cert no"]),
    ("notes", "Notes", False, ["notes", "note", "comment", "comments", "remarks"]),
]
TARGET_KEYS = [t[0] for t in TARGETS]


def norm(s):
    return re.sub(r"[^a-z0-9/]+", " ", str(s or "").lower()).strip()


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%d.%m.%Y")
    if isinstance(v, date):
        return v.strftime("%d.%m.%Y")
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def read_table(uploaded):
    """Return (headers, rows) with all cells as strings."""
    name = uploaded.name.lower()
    if name.endswith(".xlsx"):
        from openpyxl import load_workbook

        wb = load_workbook(uploaded, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        raw = [[_cell(c) for c in row] for row in ws.iter_rows(values_only=True)]
        wb.close()
    else:
        data = uploaded.read()
        for enc in ("utf-8-sig", "cp1250", "latin-1"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        raw = [[c.strip() for c in row] for row in csv.reader(io.StringIO(text), dialect)]
    raw = [r for r in raw if any(c for c in r)]
    if not raw:
        raise ValueError("The file is empty.")
    headers = [h or f"Column {i + 1}" for i, h in enumerate(raw[0])]
    rows = [r + [""] * (len(headers) - len(r)) for r in raw[1:MAX_ROWS + 1]]
    return headers, [r[: len(headers)] for r in rows]


def guess_mapping(headers):
    mapping = {}
    normalized = [norm(h) for h in headers]
    for key, label, _, aliases in TARGETS:
        for alias in [norm(label)] + aliases:
            if alias in normalized and normalized.index(alias) not in mapping.values():
                mapping[key] = normalized.index(alias)
                break
    return mapping


def parse_date(value):
    value = value.strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"'{value}' is not a date (use DD.MM.YYYY)")


STATUS_LOOKUP = {}
for _key, _label in Device.STATUS_CHOICES:
    STATUS_LOOKUP[norm(_key)] = _key
    STATUS_LOOKUP[norm(_label)] = _key


@dataclass
class RowResult:
    line: int
    action: str = "create"  # create | update | error
    errors: list = field(default_factory=list)
    values: dict = field(default_factory=dict)
    custom: dict = field(default_factory=dict)  # field_id -> raw string
    device: Device = None
    owner: User = None
    last_date: date = None
    brand_name: str = ""  # resolved/created in apply()
    model_name: str = ""
    new_brand: bool = False
    new_model: bool = False


def _custom_value(fd, raw):
    t = fd.field_type
    if t == FieldDefinition.NUMBER:
        try:
            return Decimal(raw.replace(",", "."))
        except InvalidOperation:
            raise ValueError(f"{fd.name}: '{raw}' is not a number")
    if t == FieldDefinition.DATE:
        return parse_date(raw)
    if t == FieldDefinition.CHECKBOX:
        return norm(raw) in ("1", "yes", "y", "true", "x", "ano")
    if t == FieldDefinition.DROPDOWN:
        for o in fd.options_list:
            if norm(o) == norm(raw):
                return o
        raise ValueError(f"{fd.name}: '{raw}' is not one of {', '.join(fd.options_list)}")
    if t == FieldDefinition.FILE:
        raise ValueError(f"{fd.name}: file fields cannot be imported")
    return raw


def clean_name(value):
    return " ".join(value.split())


def validate(headers, rows, mapping):
    brands = {b.name.casefold(): b for b in Manufacturer.objects.prefetch_related("fields")}
    models_by_brand = {(m.manufacturer_id, m.name.casefold()): m for m in DeviceModel.objects.prefetch_related("fields")}
    users = list(User.objects.all())
    by_login = {u.username.lower(): u for u in users}
    by_email = {u.email.lower(): u for u in users if u.email}
    by_name = {norm(u.get_full_name()): u for u in users if u.get_full_name()}
    existing = {
        d.asset_tag.lower(): d
        for d in Device.objects.select_related("manufacturer", "device_model").prefetch_related(
            "manufacturer__fields", "device_model__fields"
        )
    }
    norm_headers = [norm(h) for h in headers]
    seen = set()
    results = []

    for i, row in enumerate(rows):
        r = RowResult(line=i + 2)
        get = lambda key: row[mapping[key]].strip() if key in mapping and mapping[key] is not None else ""

        for key, label, required, _ in TARGETS:
            if required and not get(key) and not (key != "asset_tag" and existing.get(get("asset_tag").lower())):
                r.errors.append(f"{label} is empty")

        tag = get("asset_tag")
        if tag:
            if tag.lower() in seen:
                r.errors.append(f"Asset ID {tag} appears more than once in the file")
            seen.add(tag.lower())
            r.device = existing.get(tag.lower())
            r.action = "update" if r.device else "create"
        r.values["asset_tag"] = tag

        if get("owner"):
            o = get("owner").lower()
            r.owner = by_login.get(o) or by_email.get(o) or by_name.get(norm(o))
            if not r.owner:
                r.errors.append(f"Unknown owner '{get('owner')}' (create the user first)")

        if get("status"):
            status = STATUS_LOOKUP.get(norm(get("status")))
            if status:
                r.values["status"] = status
            else:
                r.errors.append(f"Unknown status '{get('status')}'")

        for key in ("name", "serial_number", "location", "notes", "certificate_no"):
            if get(key):
                r.values[key] = get(key)

        r.brand_name, r.model_name = clean_name(get("manufacturer")), clean_name(get("model"))
        if r.model_name and not r.brand_name:
            if r.device and r.device.manufacturer:
                r.brand_name = r.device.manufacturer.name
            else:
                r.errors.append("Model given without a manufacturer")
        # existing manufacturer/model whose custom fields can be filled from this row
        field_owners = []
        if r.brand_name:
            brand = brands.get(r.brand_name.casefold())
            model = models_by_brand.get((brand.pk, r.model_name.casefold())) if brand and r.model_name else None
            r.new_brand = brand is None
            r.new_model = bool(r.model_name) and model is None
            field_owners = [o for o in (brand, model) if o]
        elif r.device:
            field_owners = [o for o in (r.device.manufacturer, r.device.device_model) if o]

        if get("interval_override_months"):
            try:
                r.values["interval_override_months"] = int(Decimal(get("interval_override_months").replace(",", ".")))
            except InvalidOperation:
                r.errors.append(f"Interval '{get('interval_override_months')}' is not a number")

        if get("last_calibration_date"):
            try:
                r.last_date = parse_date(get("last_calibration_date"))
            except ValueError as e:
                r.errors.append(str(e))

        if field_owners:
            mapped_cols = {v for v in mapping.values() if v is not None}
            for fd in [fd for o in field_owners for fd in o.fields.all()]:
                if norm(fd.name) in norm_headers:
                    col = norm_headers.index(norm(fd.name))
                    if col in mapped_cols:
                        continue
                    raw = row[col].strip()
                    if not raw:
                        continue
                    try:
                        r.custom[fd.id] = (fd, _custom_value(fd, raw))
                    except ValueError as e:
                        r.errors.append(str(e))

        if r.errors:
            r.action = "error"
        results.append(r)
    return results


@transaction.atomic
def apply(results, user):
    created = updated = 0
    for r in results:
        if r.action == "error":
            continue
        values = dict(r.values)
        cert = values.pop("certificate_no", "")
        if r.action == "create":
            device = Device(owner=r.owner, **values)
            device.save()
            created += 1
            audit(user, "imported (created)", device, changes={k: (None, v) for k, v in values.items()})
        else:
            device = r.device
            changes = {}
            if r.owner and r.owner != device.owner:
                changes["owner"] = (device.owner, r.owner)
                device.owner = r.owner
            for k, v in values.items():
                if getattr(device, k) != v:
                    changes[k] = (getattr(device, k), v)
                    setattr(device, k, v)
            device.save()
            updated += 1
            if changes:
                audit(user, "imported (updated)", device, changes=changes)
        brand_changes = _apply_brand_model(device, r, user)
        if brand_changes:
            device.save(update_fields=["manufacturer", "device_model", "updated_at"])
            audit(user, "imported (brand/model)", device, changes=brand_changes)
        for fd, value in r.custom.values():
            obj, _ = DeviceFieldValue.objects.get_or_create(device=device, field=fd)
            if fd.field_type == FieldDefinition.NUMBER:
                obj.value_number = value
            elif fd.field_type == FieldDefinition.DATE:
                obj.value_date = value
            elif fd.field_type == FieldDefinition.CHECKBOX:
                obj.value_bool = value
            else:
                obj.value_text = value
            obj.save()
        if r.last_date and not device.events.filter(date=r.last_date).exists():
            CalibrationEvent.objects.create(
                device=device, date=r.last_date, result=CalibrationEvent.RESULT_NOT_RECORDED,
                certificate_no=cert, notes="Imported", created_by=user,
            )
        device.refresh_calibration_dates()
    return created, updated


def _get_or_create_ci(model, user, **lookup):
    name = lookup.pop("name")
    obj = model.objects.filter(name__iexact=name, **lookup).first()
    if obj:
        return obj
    obj = model.objects.create(name=name, created_by=user, **lookup)
    audit(user, f"{'brand' if model is Manufacturer else 'model'} added (import)", obj, changes={"Name": (None, name)})
    return obj


def _apply_brand_model(device, r, user):
    """Set manufacturer/model from the row, creating missing entries. Returns audit changes."""
    if not r.brand_name:
        return {}
    changes = {}
    brand = _get_or_create_ci(Manufacturer, user, name=r.brand_name)
    model = _get_or_create_ci(DeviceModel, user, name=r.model_name, manufacturer=brand) if r.model_name else None
    if device.manufacturer_id != brand.pk:
        changes["Manufacturer"] = (device.manufacturer, brand)
        device.manufacturer = brand
        if device.device_model_id and device.device_model.manufacturer_id != brand.pk and not model:
            changes["Model"] = (device.device_model, None)
            device.device_model = None
    if model and device.device_model_id != model.pk:
        changes["Model"] = (device.device_model, model)
        device.device_model = model
    return changes
