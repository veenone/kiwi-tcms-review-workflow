"""Plugin configuration.

Two-tier resolution:

1. Database-backed configuration — the admin can edit the ReviewConfig
   singleton and ReviewStatusTransition rows from the Django admin UI.
   These values take priority when present.

2. Django settings fallback — if the DB has no configuration yet
   (fresh install, migration in progress), settings override lookups
   kick in.

Settings fallback examples (tcms_settings_dir/review.py or local_settings.py):

    REVIEW_ALLOWED_CASE_STATUSES = ["PROPOSED", "CONFIRMED"]

    REVIEW_STATUS_TRANSITIONS = {
        ("PROPOSED", "approved"):       "CONFIRMED",
        ("PROPOSED", "needs_changes"):  "NEED_UPDATE",
        ("PROPOSED", "rejected"):       "DISABLED",
        ("CONFIRMED", "needs_changes"): "NEED_UPDATE",
    }

On first install, migration `0005_seed_default_transitions` populates the
DB with the same defaults shown above, so new installs have the common
PROPOSED → CONFIRMED / NEED_UPDATE / DISABLED workflow wired up out of
the box. The admin can edit or delete those rows at any time.
"""
from django.conf import settings
from django.db import ProgrammingError, OperationalError


# Shipped with the plugin — seeded into the DB by migration
# 0005_seed_default_transitions, and also used as the last-resort
# fallback if neither the DB nor Django settings provides anything.
DEFAULT_ALLOWED_CASE_STATUSES = ["PROPOSED"]

DEFAULT_STATUS_TRANSITIONS = [
    # (source_case_status, review_decision, target_case_status)
    ("PROPOSED",    "approved",      "CONFIRMED"),
    ("PROPOSED",    "needs_changes", "NEED_UPDATE"),
    ("PROPOSED",    "rejected",      "DISABLED"),
    ("CONFIRMED",   "needs_changes", "NEED_UPDATE"),
    # Re-review loop: resubmitting a case moves it back to PROPOSED so
    # the allowed-status filter picks it up again.
    ("NEED_UPDATE", "pending",       "PROPOSED"),
    ("DISABLED",    "pending",       "PROPOSED"),
]


def _safe_db_lookup(fn, default):
    """Run a DB lookup inside a guard — during `migrate`, before the
    tables exist, we must not raise."""
    try:
        return fn()
    except (ProgrammingError, OperationalError):
        return default


def get_allowed_case_statuses():
    """Return the list of TestCaseStatus.name values allowed for review.

    Resolution order: ReviewConfig singleton → Django setting → plugin default.
    """
    from tcms_review.models import ReviewConfig  # noqa: WPS433

    def from_db():
        config = ReviewConfig.objects.first()
        if config and config.allowed_case_statuses:
            return list(config.allowed_case_statuses)
        return None

    db_value = _safe_db_lookup(from_db, None)
    if db_value:
        return db_value
    return getattr(settings, "REVIEW_ALLOWED_CASE_STATUSES", list(DEFAULT_ALLOWED_CASE_STATUSES))


def get_status_transitions():
    """Return the (source_status, decision) -> target_status map.

    Resolution order: DB table (ReviewStatusTransition, is_active=True) →
    Django setting REVIEW_STATUS_TRANSITIONS → empty map.

    Keys in the returned dict are upper-cased source + lower-cased
    decision; values are upper-cased target. Matching is therefore
    case-insensitive.
    """
    from tcms_review.models import ReviewStatusTransition  # noqa: WPS433

    def from_db():
        rows = ReviewStatusTransition.objects.filter(is_active=True)
        if not rows.exists():
            return None
        return {
            (r.source_status.upper(), r.decision.lower()): r.target_status.upper()
            for r in rows
        }

    db_value = _safe_db_lookup(from_db, None)
    if db_value is not None:
        return db_value

    raw = getattr(settings, "REVIEW_STATUS_TRANSITIONS", {})
    normalised = {}
    for key, target in raw.items():
        if isinstance(key, tuple) and len(key) == 2:
            source, decision = key
            normalised[(source.upper(), decision.lower())] = target.upper()
    return normalised
