"""Plugin configuration. Override via Django settings.

Example in tcms_settings_dir/review.py or your own local_settings.py:

    REVIEW_ALLOWED_CASE_STATUSES = ["PROPOSED", "CONFIRMED"]

    REVIEW_STATUS_TRANSITIONS = {
        ("PROPOSED", "approved"): "CONFIRMED",
        ("PROPOSED", "rejected"): "DISABLED",
    }
"""
from django.conf import settings


def get_allowed_case_statuses():
    """Return the list of TestCaseStatus.name values allowed for review."""
    return getattr(settings, "REVIEW_ALLOWED_CASE_STATUSES", ["PROPOSED"])


def get_status_transitions():
    """Return the (source_status, decision) -> target_status map.

    When a ReviewItem.decision is set to <decision> and the linked
    TestCase.case_status.name matches <source_status>, the case is
    transitioned to <target_status>.

    Matching is case-insensitive. Unmatched decisions are no-ops.

    Returns a dict with upper-cased keys/values for comparison.
    """
    raw = getattr(settings, "REVIEW_STATUS_TRANSITIONS", {})
    normalised = {}
    for key, target in raw.items():
        if isinstance(key, tuple) and len(key) == 2:
            source, decision = key
            normalised[(source.upper(), decision.lower())] = target.upper()
    return normalised
