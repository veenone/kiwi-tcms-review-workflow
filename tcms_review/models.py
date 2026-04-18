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

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]

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
