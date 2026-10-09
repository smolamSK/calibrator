from functools import wraps

from django.core.exceptions import PermissionDenied

from .models import Device


def visible_devices(user, queryset=None):
    qs = queryset if queryset is not None else Device.objects.all()
    if not user.is_authenticated:
        return qs.none()
    if user.can_view_all:
        return qs
    return qs.filter(owner=user)


def can_view(user, device):
    return user.is_authenticated and (user.can_view_all or device.owner_id == user.id)


def can_edit(user, device):
    return user.is_authenticated and (user.can_edit_all or device.owner_id == user.id)


def can_reassign_owner(user):
    return user.is_authenticated and user.can_edit_all


def can_delete_device(user):
    return user.is_authenticated and user.is_app_admin


def admin_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_app_admin:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def editor_all_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.can_edit_all:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper
