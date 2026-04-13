from django.db import migrations


def forwards_add_perms(apps, schema_editor):
    """Grant tcms_review.* permissions to the existing 'Tester' group."""
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
