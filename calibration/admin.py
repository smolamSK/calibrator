from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    Attachment,
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


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (("Calibrator", {"fields": ("role", "email_notifications")}),)
    list_display = ("username", "email", "first_name", "last_name", "role", "is_active")
    list_filter = ("role", "is_active")


class FieldDefinitionInline(admin.TabularInline):
    model = FieldDefinition
    extra = 0
    fields = ("name", "field_type", "required", "show_in_list", "order", "help_text", "options")


class FieldValueInline(admin.TabularInline):
    model = DeviceFieldValue
    extra = 0


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = (
        "asset_tag", "name", "manufacturer", "device_model", "owner", "status", "next_calibration_date"
    )
    list_filter = ("status", "manufacturer")
    search_fields = ("asset_tag", "name", "serial_number", "manufacturer__name", "device_model__name")
    readonly_fields = ("last_calibration_date", "next_calibration_date")
    inlines = [FieldValueInline]


@admin.register(CalibrationEvent)
class CalibrationEventAdmin(admin.ModelAdmin):
    list_display = ("device", "date", "result", "certificate_no")
    list_filter = ("result",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "username", "action", "object_type", "object_repr")
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class DeviceModelInline(admin.TabularInline):
    model = DeviceModel
    extra = 0
    fields = ("name", "interval_months", "reminder_days")


@admin.register(Manufacturer)
class ManufacturerAdmin(admin.ModelAdmin):
    list_display = ("name", "interval_months", "reminder_days")
    search_fields = ("name",)
    inlines = [DeviceModelInline, FieldDefinitionInline]


@admin.register(DeviceModel)
class DeviceModelAdmin(admin.ModelAdmin):
    list_display = ("name", "manufacturer", "interval_months", "reminder_days")
    list_filter = ("manufacturer",)
    search_fields = ("name", "manufacturer__name")
    inlines = [FieldDefinitionInline]


admin.site.register(Attachment)
admin.site.register(NotificationLog)
admin.site.register(SiteSettings)
