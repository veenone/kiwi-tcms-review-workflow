"""Seed the ReviewStatusTransition table with the recommended defaults.

New installs get the PROPOSED → CONFIRMED / NEED_UPDATE / DISABLED
workflow wired up without any operator action. Admins can edit or
delete these rows from the Django admin at any time.

Idempotent: only seeds rows that don't already exist, so re-running
the migration (or re-applying after a rollback) won't overwrite
operator customisations.
"""
from django.db import migrations


DEFAULT_ROWS = [
    ("PROPOSED",  "approved",      "CONFIRMED"),
    ("PROPOSED",  "needs_changes", "NEED_UPDATE"),
    ("PROPOSED",  "rejected",      "DISABLED"),
    ("CONFIRMED", "needs_changes", "NEED_UPDATE"),
]


def forwards(apps, schema_editor):
    Transition = apps.get_model("tcms_review", "ReviewStatusTransition")
    for source, decision, target in DEFAULT_ROWS:
        Transition.objects.get_or_create(
            source_status=source,
            decision=decision,
            defaults={"target_status": target, "is_active": True},
        )


def backwards(apps, schema_editor):
    Transition = apps.get_model("tcms_review", "ReviewStatusTransition")
    for source, decision, _target in DEFAULT_ROWS:
        Transition.objects.filter(
            source_status=source, decision=decision,
        ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("tcms_review", "0004_review_config"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
