"""Django system checks for the review plugin.

Surfaces common install-time problems at `./manage.py check` time, so
operators see actionable warnings before they discover broken pages.

Checks emitted:

* ``tcms_review.W001`` — plugin tables are not present in the connected
  database. Usually means migrations weren't applied against this DB
  (a common cause: running ``migrate`` with the wrong ``KIWI_DB_*`` env).
* ``tcms_review.W002`` — no ``tcms_review.*`` rows in ``auth_permission``.
  Usually means ``django_content_type`` is in a broken state
  (legacy ``name`` NOT NULL column blocking bulk_create) or the
  post_migrate signal never fired.
* ``tcms_review.W003`` — standard Kiwi groups (Tester / Administrator)
  exist but lack the ``view_reviewrequest`` permission; users in those
  groups will see a 403 when visiting ``/reviews/``. Run
  ``./manage.py tcms_review_grant_perms``.

All three emit :class:`~django.core.checks.Warning` — non-fatal by
design, since the plugin should not stop `runserver` / gunicorn from
booting. Promote to errors by setting ``SILENCED_SYSTEM_CHECKS`` in
Django settings (or, the other way, run with ``--fail-level=WARNING``).
"""
from __future__ import annotations

from django.core.checks import Tags, Warning as DjangoWarning, register
from django.db import connection
from django.db.utils import DatabaseError


@register(Tags.database)
def check_tables_exist(app_configs, **kwargs):
    """W001 — plugin table presence."""
    if _is_skipped(app_configs):
        return []

    if not _table_exists("tcms_review_reviewrequest"):
        return [
            DjangoWarning(
                "tcms_review tables are not present in the connected database.",
                hint=(
                    "Run './manage.py migrate tcms_review'. If migrations "
                    "already ran against a different DB, verify KIWI_DB_* "
                    "environment variables (or DATABASES setting) point to "
                    "the DB the application actually uses at runtime."
                ),
                id="tcms_review.W001",
            ),
        ]
    return []


@register(Tags.database)
def check_permissions_exist(app_configs, **kwargs):
    """W002 — Permission rows for tcms_review.* exist."""
    if _is_skipped(app_configs):
        return []

    if not _table_exists("tcms_review_reviewrequest"):
        # W001 already fired; stay quiet instead of doubling up.
        return []

    try:
        from django.contrib.auth.models import Permission  # noqa: WPS433
    except Exception:  # noqa: BLE001
        return []

    try:
        exists = Permission.objects.filter(
            content_type__app_label="tcms_review",
        ).exists()
    except DatabaseError:
        return []

    if not exists:
        return [
            DjangoWarning(
                "No tcms_review.* Permission rows exist.",
                hint=(
                    "Usually means django_content_type has a broken schema "
                    "(e.g. a legacy NOT NULL 'name' column that blocks "
                    "bulk_create of new content types). Run "
                    "'./manage.py migrate contenttypes' and then "
                    "'./manage.py migrate tcms_review'. As a last resort "
                    "drop the offending column manually."
                ),
                id="tcms_review.W002",
            ),
        ]
    return []


@register(Tags.database)
def check_groups_granted(app_configs, **kwargs):
    """W003 — standard Kiwi groups have at least view_reviewrequest."""
    if _is_skipped(app_configs):
        return []

    if not _table_exists("tcms_review_reviewrequest"):
        return []

    try:
        from django.contrib.auth.models import Group, Permission  # noqa: WPS433
    except Exception:  # noqa: BLE001
        return []

    try:
        view_perm = Permission.objects.filter(
            content_type__app_label="tcms_review",
            codename="view_reviewrequest",
        ).first()
    except DatabaseError:
        return []

    if view_perm is None:
        # Covered by W002.
        return []

    ungranted = []
    for group_name in ("Tester", "Administrator"):
        try:
            group = Group.objects.get(name=group_name)
        except Group.DoesNotExist:
            continue
        except DatabaseError:
            return []
        if not group.permissions.filter(pk=view_perm.pk).exists():
            ungranted.append(group_name)

    if ungranted:
        return [
            DjangoWarning(
                "Kiwi group(s) exist but lack tcms_review view permission: "
                + ", ".join(ungranted) + ".",
                hint=(
                    "Run './manage.py tcms_review_grant_perms' to grant the "
                    "plugin's permissions to the standard Kiwi roles. "
                    "Without this, users in those groups get a 403 when "
                    "visiting /reviews/."
                ),
                id="tcms_review.W003",
            ),
        ]
    return []


def _is_skipped(app_configs):
    """Run only when this plugin is in scope of the current `check` run."""
    if app_configs is None:
        return False
    return not any(cfg.label == "tcms_review" for cfg in app_configs)


def _table_exists(table_name: str) -> bool:
    try:
        return table_name in connection.introspection.table_names()
    except DatabaseError:
        return False
