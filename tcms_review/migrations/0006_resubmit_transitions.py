"""Seed two additional status-transition rules to close the re-review loop.

When a tester resubmits a case (ReviewItem.decision reset to 'pending')
the linked TestCase should transition back out of NEED_UPDATE/DISABLED
into PROPOSED so it's picked up by the allowed-status filter for
re-review.

Idempotent: get_or_create guards against double-seeding. Reversible:
backwards deletes only these two rows, leaves the original four
rules from 0005 intact.
"""
from django.db import migrations


NEW_ROWS = [
    ("NEED_UPDATE", "pending", "PROPOSED"),
    ("DISABLED",    "pending", "PROPOSED"),
]


def forwards(apps, schema_editor):
    Transition = apps.get_model("tcms_review", "ReviewStatusTransition")
    for source, decision, target in NEW_ROWS:
        Transition.objects.get_or_create(
            source_status=source,
            decision=decision,
            defaults={"target_status": target, "is_active": True},
        )


def backwards(apps, schema_editor):
    Transition = apps.get_model("tcms_review", "ReviewStatusTransition")
    for source, decision, _target in NEW_ROWS:
        Transition.objects.filter(
            source_status=source, decision=decision,
        ).delete()


class Migration(migrations.Migration):
    # See 0005: get_or_create on SQLite can break the outer atomic
    # block via savepoint rollback, causing the schema_editor's PRAGMA
    # foreign_key_check on __exit__ to raise TransactionManagementError.
    atomic = False

    dependencies = [
        ("tcms_review", "0005_seed_default_transitions"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
