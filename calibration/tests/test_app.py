import io
from datetime import date, timedelta

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from calibration import importer
from calibration.ics import build_calendar
from calibration.models import (
    AuditLog,
    CalibrationEvent,
    Device,
    DeviceFieldValue,
    DeviceModel,
    FieldDefinition,
    Manufacturer,
    NotificationLog,
    SiteSettings,
    User,
)
from calibration.permissions import can_edit, can_view, visible_devices
from calibration.services import collect_reminders, reminder_kind, send_reminders

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


class Fixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        mk = lambda name, role: User.objects.create_user(name, f"{name}@example.com", "pw-Long-enough-123", role=role)
        cls.owner = mk("owner", User.ROLE_OWNER)
        cls.other = mk("other", User.ROLE_OWNER)
        cls.viewer = mk("viewer", User.ROLE_VIEWER_ALL)
        cls.editor = mk("editor", User.ROLE_EDITOR_ALL)
        cls.admin = mk("admin", User.ROLE_ADMIN)
        # default interval 12 months, reminders 30,7,0 (SiteSettings defaults)
        cls.brand = Manufacturer.objects.create(name="Acme")
        cls.model = DeviceModel.objects.create(manufacturer=cls.brand, name="M1")
        cls.f_range = FieldDefinition.objects.create(manufacturer=cls.brand, name="Range", field_type="text")
        cls.f_class = FieldDefinition.objects.create(
            manufacturer=cls.brand, name="Accuracy class", field_type="dropdown", options="A\nB\nC"
        )
        cls.dev = Device.objects.create(asset_tag="MM-1", name="Fluke 87", manufacturer=cls.brand, owner=cls.owner)
        cls.dev_other = Device.objects.create(asset_tag="MM-2", name="Fluke 179", manufacturer=cls.brand, owner=cls.other)


class NextDateTests(Fixture):
    def test_default_interval_and_override(self):
        CalibrationEvent.objects.create(device=self.dev, date=date(2026, 1, 31))
        self.dev.refresh_calibration_dates()
        self.assertEqual(self.dev.next_calibration_date, date(2027, 1, 31))
        self.dev.interval_override_months = 6
        self.dev.refresh_calibration_dates()
        self.assertEqual(self.dev.next_calibration_date, date(2026, 7, 31))
        self.dev.interval_override_months = 1
        self.dev.refresh_calibration_dates()
        self.assertEqual(self.dev.next_calibration_date, date(2026, 2, 28))  # month end clamp

    def test_latest_event_wins(self):
        CalibrationEvent.objects.create(device=self.dev, date=date(2026, 5, 1))
        CalibrationEvent.objects.create(device=self.dev, date=date(2025, 5, 1))
        self.dev.refresh_calibration_dates()
        self.assertEqual(self.dev.last_calibration_date, date(2026, 5, 1))

    def test_no_history(self):
        self.dev.refresh_calibration_dates()
        self.assertIsNone(self.dev.next_calibration_date)
        self.assertEqual(self.dev.due_state(), "unknown")

    def test_interval_fallback_chain(self):
        CalibrationEvent.objects.create(device=self.dev, date=date(2026, 1, 1))
        dev = Device.objects.get(pk=self.dev.pk)
        self.assertEqual((dev.effective_interval_months, dev.interval_source), (12, "default"))
        self.brand.interval_months = 6
        self.brand.save()
        dev = Device.objects.get(pk=self.dev.pk)
        self.assertEqual((dev.effective_interval_months, dev.interval_source), (6, "manufacturer"))
        self.model.interval_months = 3
        self.model.save()
        dev.device_model = self.model
        self.assertEqual((dev.effective_interval_months, dev.interval_source), (3, "model"))
        dev.interval_override_months = 2
        self.assertEqual((dev.effective_interval_months, dev.interval_source), (2, "device"))
        dev.refresh_calibration_dates()
        self.assertEqual(dev.next_calibration_date, date(2026, 3, 1))

    def test_reminder_days_fallback_chain(self):
        dev = Device.objects.get(pk=self.dev.pk)
        self.assertEqual(dev.effective_reminder_days_list, [30, 7, 0])
        self.brand.reminder_days = "14,0"
        self.brand.save()
        dev = Device.objects.get(pk=self.dev.pk)
        self.assertEqual(dev.effective_reminder_days_list, [14, 0])
        self.model.reminder_days = "60"
        self.model.save()
        dev.device_model = self.model
        self.assertEqual(dev.effective_reminder_days_list, [60])

    def test_brand_interval_change_updates_devices(self):
        CalibrationEvent.objects.create(device=self.dev, date=date(2026, 1, 1))
        self.dev.refresh_calibration_dates()
        self.client.force_login(self.editor)
        self.client.post(reverse("brand_edit", args=[self.brand.pk]), {
            "name": "Acme", "interval_months": 24, "reminder_days": "",
        })
        self.dev.refresh_from_db()
        self.assertEqual(self.dev.next_calibration_date, date(2028, 1, 1))

    def test_settings_default_change_updates_devices(self):
        CalibrationEvent.objects.create(device=self.dev, date=date(2026, 1, 1))
        self.dev.refresh_calibration_dates()
        self.client.force_login(self.admin)
        form = self.client.get(reverse("settings")).context["form"]
        data = {k: v for k, v in form.initial.items() if v is not None and k != "smtp_password"}
        data.update(default_interval_months=6, notifications_enabled="on")
        r = self.client.post(reverse("settings"), data)
        self.assertEqual(r.status_code, 302, r.content[:3000])
        self.dev.refresh_from_db()
        self.assertEqual(self.dev.next_calibration_date, date(2026, 7, 1))


class PermissionTests(Fixture):
    def test_matrix(self):
        expected = {
            # user: (view own, edit own, view other, edit other)
            "owner": (True, True, False, False),
            "viewer": (True, False, True, False),
            "editor": (True, True, True, True),
            "admin": (True, True, True, True),
        }
        for name, (vo, eo, vx, ex) in expected.items():
            u = getattr(self, name)
            self.assertEqual(can_view(u, self.dev), vo, name)
            self.assertEqual(can_edit(u, self.dev), eo, name)
            self.assertEqual(can_view(u, self.dev_other), vx, name)
            self.assertEqual(can_edit(u, self.dev_other), ex, name)
        self.assertEqual(list(visible_devices(self.owner)), [self.dev])

    def test_owner_cannot_open_foreign_device(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("device_detail", args=[self.dev_other.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("device_edit", args=[self.dev_other.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("device_detail", args=[self.dev.pk])).status_code, 200)

    def test_viewer_cannot_edit(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse("device_detail", args=[self.dev.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("event_create", args=[self.dev.pk])).status_code, 403)

    def test_admin_pages_forbidden_for_editor(self):
        self.client.force_login(self.editor)
        for name in ("user_list", "settings"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)
        self.assertEqual(self.client.get(reverse("import_upload")).status_code, 200)

    def test_owner_created_device_is_forced_to_self(self):
        self.client.force_login(self.owner)
        r = self.client.post(reverse("device_create"), {
            "asset_tag": "MM-9", "name": "New", "manufacturer": self.brand.pk, "owner": self.other.pk,
            "status": "active", f"cf_{self.f_class.pk}": "B",
        })
        self.assertEqual(r.status_code, 302, r.content[:2000])
        self.assertEqual(Device.objects.get(asset_tag="MM-9").owner, self.owner)


class DeviceFlowTests(Fixture):
    def test_create_with_custom_fields_and_initial_calibration(self):
        self.client.force_login(self.editor)
        r = self.client.post(reverse("device_create"), {
            "asset_tag": "MM-3", "name": "Keysight", "manufacturer": self.brand.pk, "owner": self.owner.pk,
            "status": "active", "initial_calibration_date": "15.03.2026",
            f"cf_{self.f_range.pk}": "0-1000 V", f"cf_{self.f_class.pk}": "A",
        })
        self.assertEqual(r.status_code, 302)
        d = Device.objects.get(asset_tag="MM-3")
        self.assertEqual(d.next_calibration_date, date(2027, 3, 15))
        values = {v.field.name: v.display() for v in d.field_values.all()}
        self.assertEqual(values, {"Range": "0-1000 V", "Accuracy class": "A"})
        self.assertTrue(AuditLog.objects.filter(device=d, action="created").exists())

    def test_invalid_dropdown_value_rejected(self):
        self.client.force_login(self.editor)
        r = self.client.post(reverse("device_edit", args=[self.dev.pk]), {
            "asset_tag": "MM-1", "name": "Fluke 87", "manufacturer": self.brand.pk, "owner": self.owner.pk,
            "status": "active", f"cf_{self.f_class.pk}": "Z",
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(DeviceFieldValue.objects.filter(device=self.dev).exists())

    def test_record_calibration_with_certificate(self):
        self.client.force_login(self.owner)
        pdf = SimpleUploadedFile("cert.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        r = self.client.post(reverse("event_create", args=[self.dev.pk]), {
            "date": "2026-09-01", "provider_type": "external", "performed_by": "Lab X",
            "result": "pass", "certificate_no": "C-77", "notes": "", "files": [pdf],
        })
        self.assertEqual(r.status_code, 302)
        self.dev.refresh_from_db()
        self.assertEqual(self.dev.next_calibration_date, date(2027, 9, 1))
        att = self.dev.attachments.get()
        r = self.client.get(reverse("attachment_download", args=[att.pk]))
        self.assertEqual(b"".join(r.streaming_content), b"%PDF-1.4 test")
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("attachment_download", args=[att.pk])).status_code, 403)
        att.file.delete(save=False)

    def test_delete_event_recalculates(self):
        e1 = CalibrationEvent.objects.create(device=self.dev, date=date(2025, 1, 1))
        e2 = CalibrationEvent.objects.create(device=self.dev, date=date(2026, 1, 1))
        self.dev.refresh_calibration_dates()
        self.client.force_login(self.owner)
        self.client.post(reverse("event_delete", args=[e2.pk]))
        self.dev.refresh_from_db()
        self.assertEqual(self.dev.last_calibration_date, e1.date)

    def test_brand_change_reload_does_not_save(self):
        brand2 = Manufacturer.objects.create(name="Mitutoyo")
        FieldDefinition.objects.create(manufacturer=brand2, name="Length", field_type="number")
        self.client.force_login(self.editor)
        r = self.client.post(reverse("device_edit", args=[self.dev.pk]), {
            "asset_tag": "MM-1", "name": "Changed", "manufacturer": brand2.pk, "owner": self.owner.pk,
            "status": "active", "_reload": "1",
        })
        self.assertContains(r, "Length")
        self.assertNotContains(r, "Accuracy class")
        self.dev.refresh_from_db()
        self.assertEqual(self.dev.name, "Fluke 87")

    def test_all_pages_render_for_each_role(self):
        CalibrationEvent.objects.create(device=self.dev, date=date(2026, 1, 1))
        self.dev.refresh_calibration_dates()
        pages = [
            reverse("dashboard"), reverse("device_list"), reverse("device_list") + f"?manufacturer={self.brand.pk}&due=ok",
            reverse("device_detail", args=[self.dev.pk]), reverse("device_create"),
            reverse("device_create") + f"?manufacturer={self.brand.pk}", reverse("profile"), reverse("password_change"),
        ]
        admin_pages = [
            reverse("brand_detail", args=[self.brand.pk]), reverse("model_detail", args=[self.model.pk]),
            reverse("brand_edit", args=[self.brand.pk]), reverse("model_edit", args=[self.model.pk]),
            reverse("brand_field_create", args=[self.brand.pk]), reverse("model_field_create", args=[self.model.pk]),
            reverse("field_edit", args=[self.f_class.pk]), reverse("field_delete", args=[self.f_class.pk]),
            reverse("user_list"), reverse("user_create"),
            reverse("settings"), reverse("audit_log"), reverse("import_upload"),
            reverse("device_edit", args=[self.dev.pk]), reverse("event_create", args=[self.dev.pk]),
            reverse("brand_list"),
        ]
        for u in (self.owner, self.viewer, self.editor, self.admin):
            self.client.force_login(u)
            for p in pages + (admin_pages if u == self.admin else []):
                self.assertEqual(self.client.get(p).status_code, 200, f"{u} {p}")

    def test_export(self):
        self.client.force_login(self.viewer)
        r = self.client.get(reverse("device_list") + "?export=csv")
        text = r.content.decode("utf-8-sig")
        self.assertIn("MM-1", text)
        self.assertIn("Accuracy class", text.splitlines()[0])
        r = self.client.get(reverse("device_list") + "?export=xlsx")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b"PK"))

    def test_login_page_and_anonymous_redirect(self):
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)
        r = self.client.get(reverse("dashboard"))
        self.assertEqual(r.status_code, 302)


@override_settings(EMAIL_BACKEND=LOCMEM)
class ReminderTests(Fixture):
    def setUp(self):
        s = SiteSettings.load()
        s.smtp_host, s.from_email = "smtp.example.com", "cal@example.com"
        s.save()
        CalibrationEvent.objects.create(device=self.dev, date=date(2025, 10, 31))
        self.dev.refresh_calibration_dates()  # due 31.10.2026

    def test_kind_selection(self):
        due = self.dev.next_calibration_date
        self.assertIsNone(reminder_kind(self.dev, due - timedelta(days=31)))
        self.assertEqual(reminder_kind(self.dev, due - timedelta(days=30)), "lead-30")
        self.assertEqual(reminder_kind(self.dev, due - timedelta(days=8)), "lead-30")
        self.assertEqual(reminder_kind(self.dev, due - timedelta(days=7)), "lead-7")
        self.assertEqual(reminder_kind(self.dev, due), "lead-0")
        self.assertEqual(reminder_kind(self.dev, due + timedelta(days=1)), "overdue-0")
        self.assertEqual(reminder_kind(self.dev, due + timedelta(days=7)), "overdue-0")
        self.assertEqual(reminder_kind(self.dev, due + timedelta(days=8)), "overdue-1")

    def test_send_once_to_owner_and_managers(self):
        today = self.dev.next_calibration_date - timedelta(days=10)
        sent = send_reminders(today)
        self.assertEqual(sorted(e for e, _ in sent), ["admin@example.com", "editor@example.com", "owner@example.com"])
        self.assertEqual(len(mail.outbox), 3)
        self.assertIn("MM-1", mail.outbox[0].body)
        self.assertEqual(send_reminders(today), [])  # no duplicates same day
        self.assertEqual(send_reminders(today + timedelta(days=1)), [])  # same threshold
        self.assertEqual(len(send_reminders(today + timedelta(days=3))), 3)  # lead-7 reached
        self.assertEqual(NotificationLog.objects.count(), 6)

    def test_retired_and_opted_out_skipped(self):
        today = self.dev.next_calibration_date
        self.owner.email_notifications = False
        self.owner.save()
        self.assertNotIn("owner@example.com", collect_reminders(today))
        self.dev.status = Device.STATUS_RETIRED
        self.dev.save()
        self.assertEqual(collect_reminders(today), {})

    def test_not_sent_without_smtp(self):
        s = SiteSettings.load()
        s.smtp_host = ""
        s.save()
        self.assertEqual(send_reminders(self.dev.next_calibration_date), [])
        self.assertEqual(NotificationLog.objects.count(), 0)


class IcsTests(Fixture):
    def test_feed(self):
        CalibrationEvent.objects.create(device=self.dev, date=date(2026, 1, 1))
        self.dev.refresh_calibration_dates()
        r = self.client.get(reverse("ics_feed", args=[self.owner.ics_token]))
        body = r.content.decode()
        self.assertEqual(r["Content-Type"], "text/calendar; charset=utf-8")
        self.assertIn("DTSTART;VALUE=DATE:20270101", body)
        self.assertIn("MM-1", body)
        self.assertNotIn("MM-2", body)
        self.assertEqual(self.client.get(reverse("ics_feed", args=["bogus"])).status_code, 404)

    def test_escaping_and_folding(self):
        self.dev.name = "Fluke; with, special chars " + "x" * 80
        self.dev.last_calibration_date = date(2026, 1, 1)
        self.dev.next_calibration_date = date(2027, 1, 1)
        body = build_calendar([self.dev])
        self.assertIn("Fluke\\; with\\, special", body)
        self.assertTrue(all(len(line.encode()) <= 75 for line in body.split("\r\n")))


class ImportTests(Fixture):
    def _upload(self, text, name="devices.csv"):
        return SimpleUploadedFile(name, text.encode("utf-8"))

    def test_csv_create_update_and_errors(self):
        csv_text = (
            "Asset ID;Name;Manufacturer;Owner;Last calibration date;Range;Accuracy class\n"
            "MM-1;Fluke 87 V;Acme;owner;01.02.2026;0-600 V;B\n"
            "MM-5;New meter;acme;other@example.com;15.06.2026;;A\n"
            "MM-6;Bad;Acme;ghost;31.02.2026;;Z\n"
        )
        headers, rows = importer.read_table(self._upload(csv_text))
        mapping = importer.guess_mapping(headers)
        self.assertEqual(mapping["last_calibration_date"], 4)
        results = importer.validate(headers, rows, mapping)
        self.assertEqual([r.action for r in results], ["update", "create", "error"])
        self.assertEqual(len(results[2].errors), 3)  # owner, date, dropdown value
        created, updated = importer.apply(results, self.admin)
        self.assertEqual((created, updated), (1, 1))
        self.dev.refresh_from_db()
        self.assertEqual(self.dev.name, "Fluke 87 V")
        self.assertEqual(self.dev.next_calibration_date, date(2027, 2, 1))
        new = Device.objects.get(asset_tag="MM-5")
        self.assertEqual(new.owner, self.other)
        self.assertEqual(new.field_values.get(field=self.f_class).value_text, "A")

    def test_xlsx_through_views(self):
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.append(["Asset", "Device name", "Owner", "Calibration date"])
        ws.append(["MM-7", "From Excel", "editor", timezone.datetime(2026, 4, 1)])
        buf = io.BytesIO()
        wb.save(buf)
        self.client.force_login(self.editor)
        r = self.client.post(reverse("import_upload"), {"file": SimpleUploadedFile("d.xlsx", buf.getvalue())})
        self.assertRedirects(r, reverse("import_preview"))
        r = self.client.get(reverse("import_preview"))
        self.assertContains(r, "MM-7")
        post = {f"map_{k}": "" if sel is None else sel for k, _, _, sel in r.context["targets"]}
        post["apply"] = "1"
        r = self.client.post(reverse("import_preview"), post)
        self.assertRedirects(r, reverse("device_list"))
        self.assertEqual(Device.objects.get(asset_tag="MM-7").next_calibration_date, date(2027, 4, 1))


class BrandModelTests(Fixture):
    def setUp(self):
        self.fluke = Manufacturer.objects.create(name="Fluke")
        self.m87 = DeviceModel.objects.create(manufacturer=self.fluke, name="87V")
        self.keysight = Manufacturer.objects.create(name="Keysight")

    def device_post(self, **extra):
        data = {"asset_tag": "MM-1", "name": "Fluke 87", "owner": self.owner.pk, "status": "active"}
        data.update(extra)
        return data

    def test_owner_quick_add_brand_and_duplicates(self):
        self.client.force_login(self.owner)
        url = reverse("manufacturer_quick_add")
        r = self.client.post(url, {"name": "  Mitutoyo  "})
        self.assertEqual(r.json()["name"], "Mitutoyo")
        self.assertFalse(r.json()["existed"])
        r = self.client.post(url, {"name": "FLUKE"})
        self.assertEqual(r.json(), {"id": self.fluke.pk, "name": "Fluke", "existed": True})
        self.assertEqual(self.client.post(url, {"name": ""}).status_code, 400)
        self.assertTrue(AuditLog.objects.filter(action="brand added", object_repr="Mitutoyo").exists())

    def test_quick_add_model(self):
        self.client.force_login(self.owner)
        url = reverse("model_quick_add")
        self.assertEqual(self.client.post(url, {"name": "179"}).status_code, 400)  # no brand
        r = self.client.post(url, {"name": "179", "manufacturer": self.fluke.pk})
        self.assertEqual(r.json()["manufacturer"], self.fluke.pk)
        r = self.client.post(url, {"name": "87v", "manufacturer": self.fluke.pk})
        self.assertEqual(r.json()["id"], self.m87.pk)
        # same model name under another brand is a different entry
        r = self.client.post(url, {"name": "87V", "manufacturer": self.keysight.pk})
        self.assertNotEqual(r.json()["id"], self.m87.pk)

    def test_quick_add_requires_login_and_post(self):
        r = self.client.post(reverse("manufacturer_quick_add"), {"name": "X"})
        self.assertEqual(r.status_code, 302)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("manufacturer_quick_add")).status_code, 405)

    def test_device_rejects_model_of_other_brand(self):
        self.client.force_login(self.editor)
        r = self.client.post(reverse("device_edit", args=[self.dev.pk]),
                             self.device_post(manufacturer=self.keysight.pk, device_model=self.m87.pk))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "different manufacturer")
        r = self.client.post(reverse("device_edit", args=[self.dev.pk]),
                             self.device_post(manufacturer=self.fluke.pk, device_model=self.m87.pk))
        self.assertEqual(r.status_code, 302)
        self.dev.refresh_from_db()
        self.assertEqual((self.dev.manufacturer, self.dev.device_model), (self.fluke, self.m87))

    def test_model_without_brand_fills_brand(self):
        self.client.force_login(self.editor)
        self.client.post(reverse("device_edit", args=[self.dev.pk]), self.device_post(device_model=self.m87.pk))
        self.dev.refresh_from_db()
        self.assertEqual(self.dev.manufacturer, self.fluke)

    def test_management_permissions_and_delete_rules(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("brand_list")).status_code, 403)
        self.client.force_login(self.editor)
        self.assertContains(self.client.get(reverse("brand_list")), "87V")
        self.dev.manufacturer, self.dev.device_model = self.fluke, self.m87
        self.dev.save()
        self.client.post(reverse("brand_delete", args=[self.fluke.pk]))
        self.client.post(reverse("model_delete", args=[self.m87.pk]))
        self.assertTrue(Manufacturer.objects.filter(pk=self.fluke.pk).exists())
        self.assertTrue(DeviceModel.objects.filter(pk=self.m87.pk).exists())
        self.client.post(reverse("brand_delete", args=[self.keysight.pk]))
        self.assertFalse(Manufacturer.objects.filter(pk=self.keysight.pk).exists())

    def test_rename_and_move_model(self):
        self.dev.manufacturer, self.dev.device_model = self.fluke, self.m87
        self.dev.save()
        self.client.force_login(self.editor)
        self.client.post(reverse("brand_edit", args=[self.fluke.pk]), {"name": "Fluke Corp."})
        r = self.client.post(reverse("brand_edit", args=[self.keysight.pk]), {"name": "fluke corp."})
        self.assertContains(r, "already exists")
        self.assertContains(self.client.get(reverse("device_detail", args=[self.dev.pk])), "Fluke Corp.")
        self.client.post(reverse("model_edit", args=[self.m87.pk]), {"manufacturer": self.keysight.pk, "name": "87V"})
        self.dev.refresh_from_db()
        self.assertEqual(self.dev.manufacturer, self.keysight)
        self.assertTrue(AuditLog.objects.filter(action="brand edited").exists())

    def test_list_filter_search_and_export(self):
        self.dev.manufacturer, self.dev.device_model = self.fluke, self.m87
        self.dev.save()
        self.client.force_login(self.viewer)
        r = self.client.get(reverse("device_list") + f"?manufacturer={self.keysight.pk}")
        self.assertNotContains(r, "MM-1")
        r = self.client.get(reverse("device_list") + "?q=87v")
        self.assertContains(r, "MM-1")
        text = self.client.get(reverse("device_list") + "?export=csv").content.decode("utf-8-sig")
        self.assertIn("Fluke;87V", text)

    def test_import_creates_and_reuses_case_insensitively(self):
        csv_text = (
            "Asset ID;Name;Owner;Manufacturer;Model\n"
            "MM-1;Fluke 87;owner;FLUKE;87v\n"
            "MM-8;Caliper;owner;Mitutoyo;CD-15\n"
            "MM-9;Caliper 2;owner;mitutoyo;CD-15\n"
            "MM-10;Orphan;owner;;X1\n"
        )
        headers, rows = importer.read_table(SimpleUploadedFile("d.csv", csv_text.encode()))
        results = importer.validate(headers, rows, importer.guess_mapping(headers))
        self.assertEqual([(r.new_brand, r.new_model) for r in results[:3]], [(False, False), (True, True), (True, True)])
        self.assertEqual(results[3].action, "error")
        importer.apply(results, self.editor)
        self.dev.refresh_from_db()
        self.assertEqual((self.dev.manufacturer, self.dev.device_model), (self.fluke, self.m87))
        self.assertEqual(Manufacturer.objects.filter(name__iexact="mitutoyo").count(), 1)
        self.assertEqual(DeviceModel.objects.filter(name="CD-15").count(), 1)
        self.assertEqual(Device.objects.get(asset_tag="MM-9").device_model.name, "CD-15")


class LookupFieldTests(Fixture):
    def test_device_form_shows_brand_and_model_fields(self):
        f_probe = FieldDefinition.objects.create(device_model=self.model, name="Probe type", field_type="text")
        self.client.force_login(self.editor)
        r = self.client.get(reverse("device_edit", args=[self.dev.pk]) + f"?manufacturer={self.brand.pk}&device_model={self.model.pk}")
        self.assertContains(r, "Accuracy class")
        self.assertContains(r, "Probe type")
        r = self.client.post(reverse("device_edit", args=[self.dev.pk]), {
            "asset_tag": "MM-1", "name": "Fluke 87", "owner": self.owner.pk, "status": "active",
            "manufacturer": self.brand.pk, "device_model": self.model.pk,
            f"cf_{self.f_class.pk}": "C", f"cf_{f_probe.pk}": "K-type",
        })
        self.assertEqual(r.status_code, 302)
        dev = Device.objects.get(pk=self.dev.pk)
        self.assertEqual(
            [(f.name, v.display() if v else "") for f, v in dev.custom_values()],
            [("Range", ""), ("Accuracy class", "C"), ("Probe type", "K-type")],
        )
        r = self.client.get(reverse("device_list") + f"?device_model={self.model.pk}")
        self.assertContains(r, "MM-1")

    def test_field_management_on_model_page(self):
        self.client.force_login(self.owner)
        url = reverse("model_field_create", args=[self.model.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.editor)
        r = self.client.post(url, {"name": "Probe type", "field_type": "text", "order": 10})
        self.assertRedirects(r, reverse("model_detail", args=[self.model.pk]))
        fd = FieldDefinition.objects.get(device_model=self.model)
        self.assertContains(self.client.get(reverse("model_detail", args=[self.model.pk])), "Probe type")
        # same name allowed on a different owner, not twice on the same one
        r = self.client.post(url, {"name": "Probe type", "field_type": "text", "order": 20})
        self.assertEqual(r.status_code, 200)
        r = self.client.post(reverse("field_edit", args=[fd.pk]), {"name": "Probe", "field_type": "text", "order": 5})
        self.assertRedirects(r, reverse("model_detail", args=[self.model.pk]))
        r = self.client.post(reverse("field_delete", args=[fd.pk]))
        self.assertRedirects(r, reverse("model_detail", args=[self.model.pk]))
        self.assertFalse(FieldDefinition.objects.filter(pk=fd.pk).exists())

    def test_list_columns_for_filtered_brand(self):
        self.f_class.show_in_list = True
        self.f_class.save()
        DeviceFieldValue.objects.create(device=self.dev, field=self.f_class, value_text="B")
        self.client.force_login(self.viewer)
        r = self.client.get(reverse("device_list") + f"?manufacturer={self.brand.pk}")
        self.assertEqual([f.name for f in r.context["extra_fields"]], ["Accuracy class"])
        self.assertEqual(self.client.get(reverse("device_list")).context["extra_fields"], [])


class HelpTests(Fixture):
    def test_user_manual_for_everyone(self):
        for u in (self.owner, self.viewer, self.editor, self.admin):
            self.client.force_login(u)
            r = self.client.get(reverse("help"))
            self.assertContains(r, 'id="recording-a-calibration"')
            self.assertContains(r, 'href="#recording-a-calibration"')  # table of contents
            self.assertContains(r, "<table>")
            self.assertContains(r, reverse("help"))  # navbar link
            self.assertEqual(reverse("help_admin") in r.content.decode(), u.can_edit_all, u)

    def test_admin_manual_for_editors_and_admins_only(self):
        for u, status in ((self.owner, 403), (self.viewer, 403), (self.editor, 200), (self.admin, 200)):
            self.client.force_login(u)
            r = self.client.get(reverse("help_admin"))
            self.assertEqual(r.status_code, status, u)
        self.assertContains(r, 'id="custom-fields"')

    def test_help_requires_login(self):
        self.assertEqual(self.client.get(reverse("help")).status_code, 302)
