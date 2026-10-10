from collections import Counter

import django.db.models.deletion
from django.db import migrations, models

import calibration.models


def categories_to_brands(apps, schema_editor):
    Category = apps.get_model("calibration", "Category")
    Device = apps.get_model("calibration", "Device")
    FieldDefinition = apps.get_model("calibration", "FieldDefinition")
    SiteSettings = apps.get_model("calibration", "SiteSettings")

    settings, _ = SiteSettings.objects.get_or_create(pk=1)
    usage = Counter(Device.objects.values_list("category_id", flat=True))
    categories = list(Category.objects.all())
    if categories:
        main = max(categories, key=lambda c: usage.get(c.pk, 0))
        settings.default_interval_months = main.default_interval_months
        settings.default_reminder_days = main.reminder_days
        settings.save()

    for category in categories:
        devices = Device.objects.filter(category=category)
        # keep each device's interval (and so its due date) unchanged
        if category.default_interval_months != settings.default_interval_months:
            devices.filter(interval_override_months__isnull=True).update(
                interval_override_months=category.default_interval_months
            )
        # fields move to the manufacturer when all the category's devices share one
        brands = set(devices.values_list("manufacturer_id", flat=True))
        fields = FieldDefinition.objects.filter(category=category)
        if len(brands) == 1 and None not in brands:
            brand_id = brands.pop()
            for fd in fields:
                name, n = fd.name, 2
                while FieldDefinition.objects.filter(manufacturer_id=brand_id, name=name).exists():
                    name, n = f"{fd.name} ({n})", n + 1
                fd.manufacturer_id, fd.name = brand_id, name
                fd.save(update_fields=["manufacturer", "name"])
        else:
            fields.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("calibration", "0002_manufacturer_devicemodel"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="default_interval_months",
            field=models.PositiveIntegerField(default=12, help_text="Used when neither the device's model nor its manufacturer sets an interval.", verbose_name="Default calibration interval (months)"),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="default_reminder_days",
            field=models.CharField(default="30,7,0", help_text="Days before the due date when reminders are sent, comma separated (e.g. 60,14,0). Used when neither the model nor the manufacturer sets them.", max_length=100, validators=[calibration.models.validate_day_list]),
        ),
        migrations.AddField(
            model_name="manufacturer",
            name="interval_months",
            field=models.PositiveIntegerField(blank=True, help_text="Leave empty to use the default from Settings.", null=True, verbose_name="Calibration interval (months)"),
        ),
        migrations.AddField(
            model_name="manufacturer",
            name="reminder_days",
            field=models.CharField(blank=True, help_text="Days before the due date when reminders are sent, comma separated (e.g. 60,14,0). Leave empty to use the default from Settings.", max_length=100, validators=[calibration.models.validate_day_list]),
        ),
        migrations.AddField(
            model_name="devicemodel",
            name="interval_months",
            field=models.PositiveIntegerField(blank=True, help_text="Leave empty to use the manufacturer's interval.", null=True, verbose_name="Calibration interval (months)"),
        ),
        migrations.AddField(
            model_name="devicemodel",
            name="reminder_days",
            field=models.CharField(blank=True, help_text="Days before the due date when reminders are sent, comma separated (e.g. 60,14,0). Leave empty to use the manufacturer's reminder days.", max_length=100, validators=[calibration.models.validate_day_list]),
        ),
        migrations.AddField(
            model_name="fielddefinition",
            name="manufacturer",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="fields", to="calibration.manufacturer"),
        ),
        migrations.AddField(
            model_name="fielddefinition",
            name="device_model",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="fields", to="calibration.devicemodel", verbose_name="model"),
        ),
        migrations.RunPython(categories_to_brands, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="fielddefinition", name="unique_field_name_per_category"),
        migrations.AlterModelOptions(name="fielddefinition", options={"ordering": ["order", "id"]}),
        migrations.RemoveField(model_name="fielddefinition", name="category"),
        migrations.AlterField(
            model_name="fielddefinition",
            name="show_in_list",
            field=models.BooleanField(default=False, help_text="Show as a column in the device list when filtered by this manufacturer or model."),
        ),
        migrations.AddConstraint(
            model_name="fielddefinition",
            constraint=models.CheckConstraint(
                condition=models.Q(manufacturer__isnull=False, device_model__isnull=True)
                | models.Q(manufacturer__isnull=True, device_model__isnull=False),
                name="field_has_one_owner",
            ),
        ),
        migrations.AddConstraint(
            model_name="fielddefinition",
            constraint=models.UniqueConstraint(condition=models.Q(("manufacturer__isnull", False)), fields=("manufacturer", "name"), name="unique_field_name_per_manufacturer"),
        ),
        migrations.AddConstraint(
            model_name="fielddefinition",
            constraint=models.UniqueConstraint(condition=models.Q(("device_model__isnull", False)), fields=("device_model", "name"), name="unique_field_name_per_model"),
        ),
        migrations.RemoveField(model_name="device", name="category"),
        migrations.AlterField(
            model_name="device",
            name="interval_override_months",
            field=models.PositiveIntegerField(blank=True, help_text="Leave empty to use the model's, manufacturer's or default interval.", null=True, verbose_name="Interval override (months)"),
        ),
        migrations.DeleteModel(name="Category"),
    ]
