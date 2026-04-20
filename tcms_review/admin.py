from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from tcms_review.models import (
    ReviewConfig,
    ReviewItem,
    ReviewRequest,
    ReviewStatusTransition,
    ReviewVote,
    WikiIntegrationConfig,
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


@admin.register(WikiIntegrationConfig)
class WikiIntegrationConfigAdmin(SimpleHistoryAdmin):
    """Singleton admin for the external wiki integration (Outline / Confluence)."""

    list_display = ("pk", "backend", "base_url", "collection_id", "verify_ssl", "updated_at")
    readonly_fields = ("updated_at",)
    fieldsets = (
        ("Connection", {
            "fields": ("backend", "base_url", "api_token", "auth_email", "collection_id"),
            "description": (
                "<b>Backend:</b> pick the wiki you're syncing to. Set to "
                "<i>Disabled</i> to turn the integration off.<br><br>"
                "<b>Outline:</b> Base URL (e.g. <code>https://outline.example.com</code>) + "
                "API token + Collection ID or URL slug. Leave Auth email empty.<br><br>"
                "<b>Confluence Cloud:</b> Base URL "
                "(<code>https://your-org.atlassian.net/wiki</code>) + Atlassian API token + "
                "the email that owns the token + the Space Key (pasted into Collection ID).<br><br>"
                "<b>Confluence Data Center:</b> Base URL "
                "(<code>https://confluence.example.com</code>) + Space Key.<br>"
                "&nbsp;&nbsp;• <i>PAT auth (recommended):</i> paste a Personal Access Token "
                "into API token and leave Auth email empty.<br>"
                "&nbsp;&nbsp;• <i>Basic auth:</i> username in Auth email, password/PAT in API token."
            ),
        }),
        ("TLS", {
            "fields": ("verify_ssl", "ca_bundle_path"),
            "description": (
                "<b>SSL: CERTIFICATE_VERIFY_FAILED</b> on the Test "
                "connection? Your wiki likely has an internal / "
                "self-signed cert. Two options:<br>"
                "&nbsp;&nbsp;• <i>Preferred:</i> set <b>CA bundle path</b> "
                "to an absolute PEM file the Kiwi host trusts "
                "(e.g. <code>/etc/ssl/certs/my-org-root.pem</code>).<br>"
                "&nbsp;&nbsp;• <i>Last resort:</i> uncheck <b>Verify "
                "SSL</b>. This exposes the sync to MITM — use only on "
                "a trusted internal network."
            ),
        }),
        ("Sync behavior", {
            "fields": ("auto_create", "auto_update", "auto_close_marker"),
            "description": (
                "Which review lifecycle events should trigger a wiki call. "
                "All sync calls run in a background thread — a broken wiki "
                "will never block a review action."
            ),
        }),
        ("Meta", {"fields": ("updated_at",)}),
    )

    def has_add_permission(self, request):
        return not WikiIntegrationConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        """Persist then probe the connection; surface the outcome as a Django message."""
        from django.contrib import messages  # noqa: WPS433
        from tcms_review.integrations.wiki.adapters import get_adapter, WikiSyncError  # noqa: WPS433

        super().save_model(request, obj, form, change)

        if not obj.is_enabled:
            messages.info(request, "Wiki integration is disabled — nothing to test.")
            return

        adapter = get_adapter(obj)
        if adapter is None:
            messages.warning(
                request,
                "Configuration incomplete — provide all required fields for the "
                "selected backend before connection can be tested.",
            )
            return

        try:
            name = adapter.test_connection()
            messages.success(
                request,
                f"Connection OK. Target {obj.get_backend_display()} "
                f"collection/space: '{name}'.",
            )
        except WikiSyncError as exc:
            messages.error(
                request, f"Connection test failed: {exc}",
            )
