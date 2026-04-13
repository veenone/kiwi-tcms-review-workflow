"""Per-session reporting helpers. Pure read-only functions."""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from tcms_review.state_machine import State, VoteDecision


def vote_breakdown(review_request) -> dict[str, int]:
    counts = {VoteDecision.APPROVED: 0, VoteDecision.REJECTED: 0, VoteDecision.NEEDS_CHANGES: 0}
    for vote in review_request.votes.all():
        counts[vote.decision] = counts.get(vote.decision, 0) + 1
    return counts


def item_breakdown(review_request) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in review_request.items.all():
        counts[item.decision] = counts.get(item.decision, 0) + 1
    return counts


def time_to_decision(review_request) -> Optional[timedelta]:
    if review_request.state not in State.TERMINAL:
        return None
    return review_request.updated_at - review_request.created_at


def participation(review_request) -> float:
    total = review_request.reviewers.count()
    if total == 0:
        return 0.0
    return review_request.votes.count() / total


def metrics(review_request) -> dict:
    return {
        "votes": vote_breakdown(review_request),
        "items": item_breakdown(review_request),
        "time_to_decision": time_to_decision(review_request),
        "participation": participation(review_request),
        "state": review_request.state,
    }
