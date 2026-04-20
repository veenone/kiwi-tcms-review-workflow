"""Shared helpers for granting tcms_review.* permissions to Kiwi groups.

Called from three places:

1. Migration 0002 — inline best-effort grant during `./manage.py migrate`
2. apps.py::ready() post_migrate handler — retry grant after core Django
   has had a chance to populate Permission rows
3. The `tcms_review_grant_perms` management command — operator-invokable
   recovery tool

Keeping the query shape in one place avoids drift between the three call
sites. All functions swallow DatabaseError so callers in early boot /
broken-schema contexts can call them without wrapping.
"""
from __future__ import annotations

from typing import Iterable

from django.db.utils import DatabaseError


# Default Kiwi TCMS roles that should be allowed to use the review plugin
# out of the box. Operators can extend via the management command's
# --group flag.
DEFAULT_GROUPS = ("Tester", "Administrator")


def get_app_permissions():
    """Return a list of Permission rows for tcms_review's content types,
    or an empty list on any DB error (missing tables, broken schema)."""
    try:
        from django.contrib.auth.models import Permission  # noqa: WPS433
    except Exception:  # noqa: BLE001
        return []

    try:
        return list(
            Permission.objects.filter(content_type__app_label="tcms_review")
        )
    except DatabaseError:
        return []


def grant_permissions_to_groups(group_names: Iterable[str] = DEFAULT_GROUPS):
    """Grant every tcms_review.* permission to each named group that
    exists. Missing groups and DB errors are silently skipped.

    Returns a dict mapping group name -> number of permissions granted
    (0 for groups that didn't exist or couldn't be reached).
    """
    from django.contrib.auth.models import Group  # noqa: WPS433

    app_perms = get_app_permissions()
    summary: dict[str, int] = {name: 0 for name in group_names}
    if not app_perms:
        return summary

    for name in group_names:
        try:
            group = Group.objects.get(name=name)
        except Group.DoesNotExist:
            continue
        except DatabaseError:
            return summary
        group.permissions.add(*app_perms)
        summary[name] = len(app_perms)

    return summary
