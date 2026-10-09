import django.db.models.deletion
import django.db.models.functions.text
from django.conf import settings
from django.db import migrations, models


def text_to_lookups(apps, schema_editor):
    Device = apps.get_model("calibration", "Device")
    Manufacturer = apps.get_model("calibration", "Manufacturer")
    DeviceModel = apps.get_model("calibration", "DeviceModel")
    for device in Device.objects.all():
        brand_name = (device.manufacturer_text or "").strip()
        model_name = (device.model_text or "").strip()
        if not brand_name and not model_name:
            continue
        brand_name = brand_name or "Unknown"
        brand = Manufacturer.objects.filter(name__iexact=brand_name).first() or Manufacturer.objects.create(name=brand_name)
        device.manufacturer = brand
        if model_name:
            device.device_model = (
                DeviceModel.objects.filter(manufacturer=brand, name__iexact=model_name).first()
                or DeviceModel.objects.create(manufacturer=brand, name=model_name)
            )
        device.save(update_fields=["manufacturer", "device_model"])


class Migration(migrations.Migration):
    dependencies = [
        ("calibration", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameField("device", "manufacturer", "manufacturer_text"),
        migrations.RenameField("device", "model", "model_text"),
        migrations.CreateModel(
            name="Manufacturer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["name"],
                "constraints": [models.UniqueConstraint(django.db.models.functions.text.Lower("name"), name="unique_manufacturer_name_ci")],
            },
        ),
        migrations.CreateModel(
            name="DeviceModel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("manufacturer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="models", to="calibration.manufacturer")),
            ],
            options={
                "verbose_name": "model",
                "ordering": ["manufacturer__name", "name"],
                "constraints": [models.UniqueConstraint(models.F("manufacturer"), django.db.models.functions.text.Lower("name"), name="unique_model_name_per_manufacturer_ci")],
            },
        ),
        migrations.AddField(
            model_name="device",
            name="manufacturer",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="devices", to="calibration.manufacturer"),
        ),
        migrations.AddField(
            model_name="device",
            name="device_model",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="devices", to="calibration.devicemodel", verbose_name="model"),
        ),
        migrations.RunPython(text_to_lookups, migrations.RunPython.noop),
        migrations.RemoveField("device", "manufacturer_text"),
        migrations.RemoveField("device", "model_text"),
    ]
