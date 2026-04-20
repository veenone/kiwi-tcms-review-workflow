from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations
from django.db.utils import DatabaseError, IntegrityError, OperationalError, ProgrammingError


def _ensure_permissions_exist():
    """Best-effort creation of Permission rows for tcms_review's models.

    Permission rows are normally created by Django's post_migrate signal,
    which fires AFTER the whole `migrate` run completes. That would leave
    this data migration (running mid-run) looking at an empty Permission
    table, so we try to force-create the rows now.

    Swallows DB errors: on installs where django_content_type still has
    the legacy NOT NULL `name` column (contenttypes migration
    0002_remove_content_type_name never applied), bulk_create of
    ContentType rows raises IntegrityError. In that case we no-op and
    rely on the post_migrate signal handler in apps.py::ready() to
    retry the grant once the core apps have finished their work.
    """
    try:
        app_config = global_apps.get_app_config("tcms_review")
    except LookupError:
        return

    # create_permissions short-circuits when models_module is falsy, but
    # during `migrate` the config may not have its module attribute set
    # yet. Stash and restore so we don't mutate the global app registry
    # for the rest of the process.
    original = getattr(app_config, "models_module", None)
    if original is None:
        app_config.models_module = True
    try:
        create_permissions(app_config, verbosity=0)
    except (IntegrityError, OperationalError, ProgrammingError, DatabaseError):
        # Schema mismatch or mid-migrate state — the post_migrate
        # handler will finish the job.
        pass
    finally:
        app_config.models_module = original


def forwards_add_perms(apps, schema_editor):
    """Grant tcms_review.* permissions to the existing 'Tester' group."""
    _ensure_permissions_exist()

    group_model = apps.get_model("auth", "Group")
    permission_model = apps.get_model("auth", "Permission")

    try:
        tester = group_model.objects.get(name="Tester")
    except group_model.DoesNotExist:
        return

    app_perms = permission_model.objects.filter(
        content_type__app_label="tcms_review"
    )
    tester.permissions.add(*app_perms)


def backwards(apps, schema_editor):
    group_model = apps.get_model("auth", "Group")
    permission_model = apps.get_model("auth", "Permission")

    try:
        tester = group_model.objects.get(name="Tester")
    except group_model.DoesNotExist:
        return

    app_perms = permission_model.objects.filter(
        content_type__app_label="tcms_review"
    )
    tester.permissions.remove(*app_perms)


class Migration(migrations.Migration):
    # Disable the outer atomic wrapper. create_permissions + get_or_create
    # use nested savepoints; on SQLite, a savepoint rollback leaves the
    # outer transaction flagged `needs_rollback`, which then blows up the
    # schema_editor's PRAGMA foreign_key_check on __exit__ with
    # TransactionManagementError ("An error occurred in the current
    # transaction. You can't execute queries until the end of the
    # 'atomic' block."). Running non-atomic lets each statement manage
    # its own transaction state independently.
    atomic = False

    dependencies = [
        ("tcms_review", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards_add_perms, backwards),
    ]
