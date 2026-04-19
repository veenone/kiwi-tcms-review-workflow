"""Build the markdown body that gets written to the wiki page."""
from django.utils import timezone


def _fmt_dt(value):
    if value is None:
        return "—"
    return value.strftime("%Y-%m-%d %H:%M")


def build_title(review_request) -> str:
    return f"[Review #{review_request.pk}] {review_request.title}"


def build_create_body(review_request) -> str:
    """Initial body when a review is first created."""
    reviewers = ", ".join(u.username for u in review_request.reviewers.all()) or "—"
    lines = [
        f"# {build_title(review_request)}",
        "",
        f"- **State:** {review_request.get_state_display()}",
        f"- **Requester:** {review_request.requester.username}",
        f"- **Reviewers:** {reviewers}",
        f"- **Due date:** {_fmt_dt(review_request.due_date)}",
        f"- **Created:** {_fmt_dt(review_request.created_at)}",
        "",
    ]
    if review_request.description:
        lines.append("## Description")
        lines.append("")
        lines.append(review_request.description)
        lines.append("")

    items = list(review_request.items.select_related("case").all())
    if items:
        lines.append("## Cases under review")
        lines.append("")
        lines.append("| # | Summary | Decision |")
        lines.append("|---|---|---|")
        for item in items:
            safe_summary = item.case.summary.replace("|", r"\|")
            lines.append(
                f"| TC-{item.case_id} | {safe_summary} | "
                f"{item.get_decision_display()} |"
            )
        lines.append("")

    lines.append("---")
    lines.append("_Synced by kiwitcms-review._")
    return "\n".join(lines)


def build_update_body(
    review_request,
    previous_state: str = "",
    event: str = "update",
    actor: str = "system",
) -> str:
    """Append-only changelog entry."""
    stamp = timezone.now().strftime("%Y-%m-%d %H:%M")
    current = review_request.get_state_display()
    if event == "state_changed" and previous_state:
        headline = (
            f"## [{stamp}] State changed: {previous_state} → {current}"
        )
    else:
        headline = f"## [{stamp}] Updated ({event}) by {actor}"

    lines = [
        "",
        headline,
        "",
        f"- **Current state:** {current}",
        f"- **Approvals:** "
        f"{review_request.votes.filter(decision='approved').count()}  "
        f"| **Rejections:** "
        f"{review_request.votes.filter(decision='rejected').count()}  "
        f"| **Changes requested:** "
        f"{review_request.votes.filter(decision='needs_changes').count()}",
        "",
    ]
    return "\n".join(lines)
