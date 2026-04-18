"""Plugin configuration. Override via Django settings.

Example in tcms_settings_dir/review.py or your own local_settings.py:

    REVIEW_ALLOWED_CASE_STATUSES = ["PROPOSED", "CONFIRMED"]

    # Auto-transition the linked TestCase.case_status when a per-case
    # review decision is set. Map keys are (case_status_name, decision),
    # matched case-insensitively. Values are target case status names.
    #
    # Decision values come from tcms_review.state_machine.VoteDecision
    # (same values used on ReviewItem.decision):
    #   "approved"       — case was accepted
    #   "rejected"       — case was rejected
    #   "needs_changes"  — reviewer requested changes
    #
    # A typical workflow:
    REVIEW_STATUS_TRANSITIONS = {
        ("PROPOSED", "approved"):      "CONFIRMED",     # accepted → confirmed
        ("PROPOSED", "needs_changes"): "NEED_UPDATE",   # changes requested → need update
        ("PROPOSED", "rejected"):      "DISABLED",      # rejected → disabled
        # You can also transition cases that were confirmed earlier
        # but now need another round of review:
        ("CONFIRMED", "needs_changes"): "NEED_UPDATE",
    }

By default (no REVIEW_STATUS_TRANSITIONS) the plugin does NOT touch
TestCase statuses. Set the mapping deliberately — the target statuses
must already exist as TestCaseStatus rows in your Kiwi install.
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

    Matching is case-insensitive. Unmatched (source, decision) pairs are
    no-ops — the TestCase status is left alone.

    Returns a dict with upper-cased source keys and lower-cased decision
    keys so the signal handler's lookup can be deterministic.
    """
    raw = getattr(settings, "REVIEW_STATUS_TRANSITIONS", {})
    normalised = {}
    for key, target in raw.items():
        if isinstance(key, tuple) and len(key) == 2:
            source, decision = key
            normalised[(source.upper(), decision.lower())] = target.upper()
    return normalised
