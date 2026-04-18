from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from tcms_review.models import (
    ReviewConfig,
    ReviewItem,
    ReviewRequest,
    ReviewStatusTransition,
    ReviewVote,
)


@admin.register(ReviewRequest)
class ReviewRequestAdmin(SimpleHistoryAdmin):
    list_display = ("pk", "title", "state", "requester", "due_date", "created_at")
    list_filter = ("state",)
    search_fields = ("title", "description")


@admin.register(ReviewItem)
class ReviewItemAdmin(SimpleHistoryAdmin):
    list_display = ("pk", "review_request", "case", "decision", "updated_at")
    list_filter = ("decision",)


@admin.register(ReviewVote)
class ReviewVoteAdmin(SimpleHistoryAdmin):
    list_display = ("pk", "review_request", "reviewer", "decision", "voted_at")
    list_filter = ("decision",)


# ─── Plugin configuration (kept at the top of the admin app) ──────────


@admin.register(ReviewConfig)
class ReviewConfigAdmin(admin.ModelAdmin):
    """Singleton admin — always shows exactly one configuration row."""

    list_display = ("pk", "allowed_case_statuses_display", "updated_at")
    readonly_fields = ("updated_at",)
    fieldsets = (
        (None, {
            "fields": ("allowed_case_statuses", "updated_at"),
            "description": (
                "<b>Allowed case statuses:</b> JSON list of "
                "TestCaseStatus.name values that can be submitted for review, "
                "e.g. <code>[\"PROPOSED\", \"CONFIRMED\"]</code>. "
                "Leave empty to fall back to the REVIEW_ALLOWED_CASE_STATUSES "
                "Django setting (default: <code>[\"PROPOSED\"]</code>)."
            ),
        }),
    )

    def has_add_permission(self, request):
        # Singleton — admins can only have one row
        return not ReviewConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Allowed case statuses")
    def allowed_case_statuses_display(self, obj):
        if not obj.allowed_case_statuses:
            return "— (using Django settings fallback)"
        return ", ".join(obj.allowed_case_statuses)


@admin.register(ReviewStatusTransition)
class ReviewStatusTransitionAdmin(SimpleHistoryAdmin):
    """One row per transition rule. Fully editable from the Kiwi admin."""

    list_display = ("source_status", "decision", "target_status", "is_active", "updated_at")
    list_filter = ("decision", "is_active")
    search_fields = ("source_status", "target_status")
    list_editable = ("is_active",)
    ordering = ("source_status", "decision")
    fieldsets = (
        (None, {
            "fields": ("source_status", "decision", "target_status", "is_active"),
            "description": (
                "<b>Source status:</b> the TestCaseStatus.name that a case "
                "must currently hold for this rule to apply.<br>"
                "<b>Decision:</b> the per-case decision that triggers the rule.<br>"
                "<b>Target status:</b> the TestCaseStatus.name to transition the "
                "case to (must exist in Kiwi).<br>"
                "Matching is case-insensitive. Uncheck <i>Is active</i> to "
                "temporarily disable a rule without deleting it."
            ),
        }),
    )
