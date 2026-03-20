"""
ERP-native permission classes for courier APIs.
"""

import logging

from rest_framework import permissions

from accounts.permissions import has_permission


logger = logging.getLogger("courier")

COURIER_OPERATOR_ROLES = {
    "admin",
    "super_user",
    "operation_controller",
    "operation_manager",
    "operation_coordinator",
    "warehouse_manager",
    "backoffice",
}

COURIER_MANAGER_ROLES = {
    "admin",
    "super_user",
    "operation_controller",
    "operation_manager",
    "warehouse_manager",
    "backoffice",
}


def _user_role(user):
    return getattr(user, "role", None)


def user_can_operate_courier(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    role = _user_role(user)
    return role in COURIER_OPERATOR_ROLES or has_permission(user, "rate_cards", "view_all")


def user_can_manage_courier(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    role = _user_role(user)
    return role in COURIER_MANAGER_ROLES or has_permission(user, "rate_cards", "edit")


class IsCourierOperator(permissions.BasePermission):
    message = "ERP login with courier access is required."

    def has_permission(self, request, view):
        allowed = user_can_operate_courier(getattr(request, "user", None))
        if not allowed:
            logger.warning(
                "COURIER_ACCESS_DENIED: user=%s path=%s method=%s",
                getattr(getattr(request, "user", None), "username", "anonymous"),
                getattr(request, "path", ""),
                getattr(request, "method", ""),
            )
        return allowed


class IsCourierManager(permissions.BasePermission):
    message = "ERP courier manager access is required."

    def has_permission(self, request, view):
        allowed = user_can_manage_courier(getattr(request, "user", None))
        if not allowed:
            logger.warning(
                "COURIER_MANAGER_ACCESS_DENIED: user=%s path=%s method=%s",
                getattr(getattr(request, "user", None), "username", "anonymous"),
                getattr(request, "path", ""),
                getattr(request, "method", ""),
            )
        return allowed

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsAdminToken(IsCourierOperator):
    """
    Backward-compatible alias for older courier code.

    The standalone X-Admin-Token flow is intentionally bypassed in ERP mode.
    """
    pass
