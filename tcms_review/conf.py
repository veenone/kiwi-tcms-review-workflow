"""Plugin configuration. Override via Django settings if needed.

Example in your settings (or tcms_settings_dir/review.py):

    REVIEW_ALLOWED_CASE_STATUSES = ["PROPOSED", "CONFIRMED"]

If not set, only test cases with status name == "PROPOSED" can be
submitted for review.
"""
from django.conf import settings


def get_allowed_case_statuses():
    """Return the list of TestCaseStatus.name values allowed for review."""
    return getattr(settings, "REVIEW_ALLOWED_CASE_STATUSES", ["PROPOSED"])
