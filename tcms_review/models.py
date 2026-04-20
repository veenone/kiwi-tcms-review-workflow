from django.conf import settings
from django.db import models
from django.urls import reverse
from simple_history.models import HistoricalRecords

from tcms_review.state_machine import State, VoteDecision, VoteSnapshot, transition


class ReviewRequest(models.Model):
    title = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True, default="")
    state = models.CharField(
        max_length=24,
        choices=State.CHOICES,
        default=State.IN_REVIEW,
        db_index=True,
    )
    due_date = models.DateTimeField(null=True, blank=True)
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requested_reviews",
    )
    reviewers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="review_assignments",
        blank=True,
    )
    cases = models.ManyToManyField(
        "testcases.TestCase",
        through="ReviewItem",
        related_name="review_requests",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    # External wiki page identifier — URL/slug for Outline, pageId for
    # Confluence. Populated by the wiki-sync signal handler; empty when
    # integration is disabled or the create call hasn't succeeded yet.
    wiki_page_id = models.CharField(max_length=128, blank=True, default="")

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["state", "due_date"],
                name="tcms_review_req_state_due_idx",
            ),
        ]

    def __str__(self):
        return f"ReviewRequest #{self.pk}: {self.title}"

    def get_absolute_url(self):
        return reverse("review-get", args=[self.pk])

    @property
    def is_locked(self) -> bool:
        """Approved requests are locked for further modification.

        Cancelled requests are not locked in the same sense — they stay
        immutable by state-machine rule, but the server never refuses
        an idempotent save for them. "Locked" in this context means the
        HTML views and RPC methods actively refuse to mutate the object.
        """
        return self.state == State.APPROVED

    @property
    def has_pending_items(self) -> bool:
        """True if any ReviewItem.decision is still PENDING.

        Reviewers cannot cast their final vote until every attached case
        has a per-case decision.
        """
        return self.items.filter(decision=ReviewItem.PENDING).exists()

    def recalculate_state(self) -> str:
        """Recompute state from current votes and persist if it changed.

        Cancelled or approved requests are immutable.
        """
        if self.state in (State.CANCELLED, State.APPROVED):
            return self.state

        snapshots = [
            VoteSnapshot(reviewer_id=v.reviewer_id, decision=v.decision)
            for v in self.votes.all()
        ]
        next_state = transition(self.reviewers.count(), snapshots)
        if next_state != self.state:
            self.state = next_state
            self.save(update_fields=["state", "updated_at"])
        return self.state


class ReviewItem(models.Model):
    """Through model linking a ReviewRequest to a TestCase, with per-case decision."""

    PENDING = "pending"
    DECISION_CHOICES = [
        (PENDING, "Pending"),
        (VoteDecision.APPROVED, "Approved"),
        (VoteDecision.REJECTED, "Rejected"),
        (VoteDecision.NEEDS_CHANGES, "Needs changes"),
    ]

    review_request = models.ForeignKey(
        ReviewRequest,
        on_delete=models.CASCADE,
        related_name="items",
    )
    case = models.ForeignKey(
        "testcases.TestCase",
        on_delete=models.CASCADE,
        related_name="review_items",
    )
    decision = models.CharField(
        max_length=24,
        choices=DECISION_CHOICES,
        default=PENDING,
    )
    comment = models.TextField(blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        unique_together = [("review_request", "case")]


class ReviewConfig(models.Model):
    """Singleton row holding plugin-wide configuration that the admin can
    tweak via the Django admin. There's always exactly one row (pk=1).

    Values stored here take priority over the Django settings fallbacks
    in tcms_review.conf, so operators can tune the plugin at runtime
    without restarting the Kiwi process or editing a settings file.
    """

    SINGLETON_PK = 1

    allowed_case_statuses = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "List of TestCaseStatus.name values allowed for review. "
            "Leave empty to fall back to REVIEW_ALLOWED_CASE_STATUSES "
            "(default: ['PROPOSED'])."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Review plugin configuration"
        verbose_name_plural = "Review plugin configuration"

    def __str__(self):
        return "Review plugin configuration"

    def save(self, *args, **kwargs):
        # Enforce singleton — always write the same pk
        self.pk = self.SINGLETON_PK
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return obj


class ReviewStatusTransition(models.Model):
    """One row per (source_status, decision) → target_status rule.

    When a ReviewItem.decision is set and matches (source_status,
    decision), the linked TestCase.case_status is transitioned to
    target_status automatically.

    Editable from the Django admin. Matching is case-insensitive.
    """

    DECISION_CHOICES = [
        ("approved", "Approved"),
        ("needs_changes", "Needs changes"),
        ("rejected", "Rejected"),
        ("pending", "Pending (resubmit)"),
    ]

    source_status = models.CharField(
        max_length=100,
        help_text="TestCaseStatus.name that triggers the transition.",
    )
    decision = models.CharField(
        max_length=32,
        choices=DECISION_CHOICES,
    )
    target_status = models.CharField(
        max_length=100,
        help_text="TestCaseStatus.name to transition to.",
    )
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        unique_together = [("source_status", "decision")]
        ordering = ["source_status", "decision"]
        verbose_name = "Review status transition"
        verbose_name_plural = "Review status transitions"

    def __str__(self):
        return f"{self.source_status} + {self.get_decision_display()} → {self.target_status}"


class ReviewVote(models.Model):
    review_request = models.ForeignKey(
        ReviewRequest,
        on_delete=models.CASCADE,
        related_name="votes",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="review_votes",
    )
    decision = models.CharField(max_length=24, choices=VoteDecision.CHOICES)
    comment = models.TextField(blank=True, default="")
    voted_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        unique_together = [("review_request", "reviewer")]


class WikiIntegrationConfig(models.Model):
    """Singleton — holds credentials and preferences for syncing reviews
    to an external wiki (Outline or Confluence). Editable from the
    Django admin at /admin/tcms_review/wikiintegrationconfig/."""

    SINGLETON_PK = 1

    BACKEND_DISABLED = "disabled"
    BACKEND_OUTLINE = "outline"
    BACKEND_CONFLUENCE = "confluence"
    BACKEND_CHOICES = [
        (BACKEND_DISABLED, "Disabled"),
        (BACKEND_OUTLINE, "Outline"),
        (BACKEND_CONFLUENCE, "Confluence"),
    ]

    backend = models.CharField(
        max_length=16,
        choices=BACKEND_CHOICES,
        default=BACKEND_DISABLED,
        help_text="Which wiki to sync reviews to. 'Disabled' skips sync entirely.",
    )
    base_url = models.URLField(
        blank=True,
        help_text="Wiki base URL, e.g. https://outline.example.com or "
                  "https://example.atlassian.net/wiki",
    )
    api_token = models.CharField(
        max_length=255,
        blank=True,
        help_text="API token (Outline: 'ol_api_...'; Confluence: an "
                  "atlassian.com API token paired with the email below).",
    )
    auth_email = models.EmailField(
        blank=True,
        help_text="Confluence only — the email address that owns the API token.",
    )
    collection_id = models.CharField(
        max_length=128,
        blank=True,
        help_text="Outline collection UUID or Confluence space key where "
                  "review pages are created.",
    )
    auto_create = models.BooleanField(
        default=True,
        help_text="Create a wiki page when a ReviewRequest is first saved.",
    )
    auto_update = models.BooleanField(
        default=True,
        help_text="Append a changelog entry on every state change.",
    )
    auto_close_marker = models.BooleanField(
        default=True,
        help_text="Mark the page as 'Approved' / 'Closed' when the review "
                  "reaches a terminal state.",
    )
    verify_ssl = models.BooleanField(
        default=True,
        help_text="Verify the wiki server's TLS certificate. Leave on "
                  "for public instances. Uncheck ONLY for internal "
                  "deployments with self-signed certs — doing so also "
                  "exposes you to MITM, so prefer providing a CA bundle "
                  "below instead.",
    )
    ca_bundle_path = models.CharField(
        max_length=512,
        blank=True,
        default="",
        help_text="Absolute path to a PEM-encoded CA bundle the server "
                  "trusts. Use this for internal wikis instead of "
                  "disabling verification. Ignored when empty.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords(excluded_fields=["api_token"])

    class Meta:
        verbose_name = "Wiki integration configuration"
        verbose_name_plural = "Wiki integration configuration"

    def __str__(self):
        return f"Wiki integration — {self.get_backend_display()}"

    def save(self, *args, **kwargs):
        # Enforce singleton — always write the same pk
        self.pk = self.SINGLETON_PK
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return obj

    @property
    def is_enabled(self):
        return self.backend != self.BACKEND_DISABLED and bool(self.base_url)

    @property
    def requests_verify(self):
        """Resolve the fields into the value expected by requests' ``verify=``
        argument. Priority: CA bundle path (if set) → verify_ssl bool.
        """
        if self.ca_bundle_path:
            return self.ca_bundle_path
        return bool(self.verify_ssl)
