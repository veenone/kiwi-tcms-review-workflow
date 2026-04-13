"""Pure state machine for review requests. No Django imports — unit-testable."""
from __future__ import annotations

from dataclasses import dataclass


class State:
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"
    CANCELLED = "cancelled"

    CHOICES = [
        (IN_REVIEW, "In review"),
        (APPROVED, "Approved"),
        (REJECTED, "Rejected"),
        (CHANGES_REQUESTED, "Changes requested"),
        (CANCELLED, "Cancelled"),
    ]

    TERMINAL = frozenset({APPROVED, REJECTED, CANCELLED})


class VoteDecision:
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CHANGES = "needs_changes"

    CHOICES = [
        (APPROVED, "Approve"),
        (REJECTED, "Reject"),
        (NEEDS_CHANGES, "Request changes"),
    ]


@dataclass(frozen=True)
class VoteSnapshot:
    reviewer_id: int
    decision: str


def transition(reviewer_count: int, votes: list[VoteSnapshot]) -> str:
    """Compute the next state given the reviewer roster and current votes.

    Cancellation is owner-driven and never produced here. The caller should
    short-circuit when the request is already cancelled.
    """
    decisions = {v.decision for v in votes}

    if VoteDecision.REJECTED in decisions:
        return State.REJECTED

    if VoteDecision.NEEDS_CHANGES in decisions:
        return State.CHANGES_REQUESTED

    voted_reviewers = {v.reviewer_id for v in votes}
    all_voted = reviewer_count > 0 and len(voted_reviewers) >= reviewer_count
    all_approved = all(v.decision == VoteDecision.APPROVED for v in votes)
    if all_voted and all_approved:
        return State.APPROVED

    return State.IN_REVIEW
