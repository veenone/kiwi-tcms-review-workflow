from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations


def _ensure_permissions_exist():
    """Permission rows are created by Django's post_migrate signal, which
    fires AFTER the whole `migrate` run completes. That leaves this data
    migration (which runs mid-run) looking at an empty Permission table.

    Calling create_permissions explicitly for our own app config forces
    the Permission rows to exist NOW so the grant below can find them.
    """
    app_config = global_apps.get_app_config("tcms_review")
    app_config.models_module = app_config.models_module or True
    create_permissions(app_config, verbosity=0)


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
    dependencies = [
        ("tcms_review", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards_add_perms, backwards),
    ]
