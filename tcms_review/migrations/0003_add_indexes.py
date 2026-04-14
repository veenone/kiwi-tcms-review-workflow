from django.db import migrations, models


class Migration(migrations.Migration):
    """Compound indexes for the query patterns used by list and dashboard views.

    Kept in its own migration per the project's database-migration rule —
    indexes should roll back independently of schema changes.

    - (state, due_date):
        ReviewRequest list view filters by state and orders by due_date;
        the dashboard widget ("Pending my review") does the same
    - (reviewer, review_request):
        The PendingMineJSON view and ReviewVote.cast hot path both look
        up votes by reviewer for a given request. The existing
        unique_together on ReviewVote covers the index on this shape,
        so this migration only adds the one compound index missing
    """

    dependencies = [
        ("tcms_review", "0002_add_permissions"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="reviewrequest",
            index=models.Index(
                fields=["state", "due_date"],
                name="tcms_review_req_state_due_idx",
            ),
        ),
    ]
