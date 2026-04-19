"""Build the markdown bodies that get written to the wiki page.

Three kinds of content:
- Initial page body (build_create_body)
- Appended changelog entries for request state changes
  (build_update_body)
- Appended changelog entries for per-case decisions and per-reviewer
  votes (build_item_decision_body, build_vote_cast_body)

All builders return plain markdown. Adapters render that however their
backend prefers (Outline: stored verbatim; Confluence: converted to
XHTML storage format).
"""
from django.utils import timezone


def _fmt_dt(value):
    if value is None:
        return "—"
    return value.strftime("%Y-%m-%d %H:%M")


def _safe_cell(text):
    return (text or "").replace("|", r"\|").replace("\n", " ").strip() or "—"


def build_title(review_request) -> str:
    return f"[Review #{review_request.pk}] {review_request.title}"


def _cases_table(review_request) -> list[str]:
    """Full cases table with current decision, comment, and last-updated
    timestamp — the 'all test cases added for review' view."""
    items = list(
        review_request.items
        .select_related("case", "case__case_status")
        .order_by("case_id")
    )
    if not items:
        return ["_No cases attached to this review yet._", ""]

    lines = [
        "| # | Test case | Kiwi status | Decision | Comment | Last updated |",
        "|---|---|---|---|---|---|",
    ]
    for item in items:
        case_status = getattr(item.case.case_status, "name", "—") if item.case.case_status_id else "—"
        lines.append(
            f"| TC-{item.case_id} "
            f"| {_safe_cell(item.case.summary)} "
            f"| {case_status} "
            f"| {item.get_decision_display()} "
            f"| {_safe_cell(item.comment)} "
            f"| {_fmt_dt(item.updated_at)} |"
        )
    return lines + [""]


def _votes_table(review_request) -> list[str]:
    """Per-reviewer current vote state (latest per reviewer)."""
    votes = list(review_request.votes.select_related("reviewer").order_by("reviewer__username"))
    reviewers = list(review_request.reviewers.order_by("username"))

    if not reviewers:
        return []

    voted_by = {v.reviewer_id: v for v in votes}

    lines = [
        "## Reviewers & current votes",
        "",
        "| Reviewer | Decision | Comment | Voted at |",
        "|---|---|---|---|",
    ]
    for reviewer in reviewers:
        v = voted_by.get(reviewer.pk)
        if v is None:
            lines.append(
                f"| {_safe_cell(reviewer.username)} | Pending | — | — |"
            )
        else:
            lines.append(
                f"| {_safe_cell(reviewer.username)} "
                f"| {v.get_decision_display()} "
                f"| {_safe_cell(v.comment)} "
                f"| {_fmt_dt(v.voted_at)} |"
            )
    return lines + [""]


def build_create_body(review_request) -> str:
    """Initial body when a review is first created. Includes the full
    set of attached cases + their decisions, plus reviewer roster."""
    reviewers = ", ".join(u.username for u in review_request.reviewers.all()) or "—"

    lines = [
        f"# {build_title(review_request)}",
        "",
        "## Summary",
        "",
        f"- **State:** {review_request.get_state_display()}",
        f"- **Requester:** {review_request.requester.username}",
        f"- **Reviewers:** {reviewers}",
        f"- **Due date:** {_fmt_dt(review_request.due_date)}",
        f"- **Created:** {_fmt_dt(review_request.created_at)}",
        "",
    ]

    if review_request.description:
        lines.extend([
            "## Description",
            "",
            review_request.description,
            "",
        ])

    lines.extend([
        "## Cases under review",
        "",
    ])
    lines.extend(_cases_table(review_request))

    votes_block = _votes_table(review_request)
    if votes_block:
        lines.extend(votes_block)

    lines.extend([
        "---",
        "_Synced by kiwitcms-review. Further changes will be appended below._",
        "",
    ])
    return "\n".join(lines)


def build_update_body(
    review_request,
    previous_state: str = "",
    event: str = "update",
    actor: str = "system",
) -> str:
    """Append-only changelog entry for request-state changes."""
    stamp = timezone.now().strftime("%Y-%m-%d %H:%M")
    current = review_request.get_state_display()

    if event == "state_changed" and previous_state:
        headline = f"## [{stamp}] State changed: {previous_state} → {current}"
    else:
        headline = f"## [{stamp}] Updated ({event}) by {actor}"

    approved = review_request.votes.filter(decision="approved").count()
    rejected = review_request.votes.filter(decision="rejected").count()
    changes = review_request.votes.filter(decision="needs_changes").count()

    lines = [
        "",
        headline,
        "",
        f"- **Current state:** {current}",
        f"- **Votes:** {approved} approved · {rejected} rejected · "
        f"{changes} changes requested",
        "",
        "### Cases at this point",
        "",
    ]
    lines.extend(_cases_table(review_request))
    return "\n".join(lines)


def build_item_decision_body(
    item,
    previous_decision: str,
    actor: str = "system",
) -> str:
    """Append-only entry for when a reviewer sets / changes a per-case
    decision. Shows old → new, the comment, and who did it."""
    stamp = timezone.now().strftime("%Y-%m-%d %H:%M")

    prev_label = (previous_decision or "pending").replace("_", " ").title()
    current_label = item.get_decision_display()

    # Action verb — describe what the reviewer did in natural terms.
    action = "updated the decision on"
    if not previous_decision:
        action = "set the decision on"
    elif previous_decision == item.decision:
        action = "kept the decision on"

    lines = [
        "",
        f"## [{stamp}] Case TC-{item.case_id}: {prev_label} → {current_label}",
        "",
        f"- **Case:** TC-{item.case_id} — "
        f"{_safe_cell(item.case.summary) if item.case_id else '—'}",
        f"- **Reviewer:** {actor}",
        f"- **Action:** {actor} {action} TC-{item.case_id}.",
        f"- **Previous decision:** {prev_label}",
        f"- **New decision:** {current_label}",
    ]
    if item.comment:
        lines.extend([
            "- **Comment:**",
            "",
            f"> {item.comment.replace(chr(10), chr(10) + '> ')}",
        ])
    lines.append("")
    return "\n".join(lines)


def build_vote_cast_body(vote, previous_decision: str = "", actor: str = "system") -> str:
    """Append-only entry for when a reviewer casts / revises an overall
    vote on the request."""
    stamp = timezone.now().strftime("%Y-%m-%d %H:%M")
    current_label = vote.get_decision_display()

    if previous_decision:
        prev_label = previous_decision.replace("_", " ").title()
        headline = f"## [{stamp}] Vote updated by {actor}: {prev_label} → {current_label}"
    else:
        headline = f"## [{stamp}] Vote cast by {actor}: {current_label}"

    lines = [
        "",
        headline,
        "",
        f"- **Reviewer:** {actor}",
        f"- **Decision:** {current_label}",
    ]
    if vote.comment:
        lines.extend([
            "- **Comment:**",
            "",
            f"> {vote.comment.replace(chr(10), chr(10) + '> ')}",
        ])
    lines.append("")
    return "\n".join(lines)
