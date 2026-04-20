"""Build the markdown body that gets written to the wiki page.

The wiki page body is re-generated in full on every sync — summary
(with emoji verdicts), current cases table, current reviewer votes
table, and a chronological changelog reconstructed from the plugin's
HistoricalRecords. Every event writes the whole thing with
`append=False`, so the page is always an accurate reflection of the
current review state.
"""
from __future__ import annotations

from django.utils import timezone


# ─── Formatting helpers ──────────────────────────────────────────────


def _fmt_dt(value) -> str:
    if value is None:
        return "—"
    return value.strftime("%Y-%m-%d %H:%M")


def _safe_cell(text) -> str:
    return (text or "").replace("|", r"\|").replace("\n", " ").strip() or "—"


# Emoji verdicts for the summary section.
_DECISION_EMOJI = {
    "pending": "⏳",
    "approved": "✅",
    "needs_changes": "⚠️",
    "rejected": "❌",
}


_STATE_EMOJI = {
    "in_review": "🔍",
    "approved": "✅",
    "rejected": "❌",
    "changes_requested": "⚠️",
    "cancelled": "🚫",
}


def build_title(review_request) -> str:
    return f"[Review #{review_request.pk}] {review_request.title}"


# ─── Top-section builders (fresh snapshot) ───────────────────────────


def _verdict_lines(review_request) -> list[str]:
    """Per-case verdict bullets with emojis — a quick at-a-glance
    summary that sits at the top of the page."""
    items = list(
        review_request.items.select_related("case").order_by("case_id")
    )
    if not items:
        return ["- _No cases attached yet._"]
    lines = []
    for item in items:
        emoji = _DECISION_EMOJI.get(item.decision, "•")
        summary = _safe_cell(item.case.summary)
        lines.append(
            f"  - {emoji} TC-{item.case_id} {summary} — "
            f"**{item.get_decision_display()}**"
        )
    return lines


def _cases_table_lines(review_request) -> list[str]:
    """Full cases table reflecting the current database state."""
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
        case_status = (
            getattr(item.case.case_status, "name", "—")
            if item.case.case_status_id else "—"
        )
        emoji = _DECISION_EMOJI.get(item.decision, "")
        decision_cell = f"{emoji} {item.get_decision_display()}".strip()
        lines.append(
            f"| TC-{item.case_id} "
            f"| {_safe_cell(item.case.summary)} "
            f"| {case_status} "
            f"| {decision_cell} "
            f"| {_safe_cell(item.comment)} "
            f"| {_fmt_dt(item.updated_at)} |"
        )
    return lines + [""]


def _votes_table_lines(review_request) -> list[str]:
    """Per-reviewer vote snapshot (latest per reviewer)."""
    votes = list(
        review_request.votes.select_related("reviewer")
        .order_by("reviewer__username")
    )
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
                f"| {_safe_cell(reviewer.username)} | ⏳ Pending | — | — |"
            )
        else:
            emoji = _DECISION_EMOJI.get(v.decision, "")
            lines.append(
                f"| {_safe_cell(reviewer.username)} "
                f"| {emoji} {v.get_decision_display()} "
                f"| {_safe_cell(v.comment)} "
                f"| {_fmt_dt(v.voted_at)} |"
            )
    return lines + [""]


def _build_top_section(review_request) -> list[str]:
    """Everything above the changelog marker — title, summary with
    per-case verdict bullets, full cases table, reviewer vote table."""
    reviewer_names = ", ".join(
        u.username for u in review_request.reviewers.all()
    ) or "—"
    state_emoji = _STATE_EMOJI.get(review_request.state, "")

    lines = [
        f"# {build_title(review_request)}",
        "",
        "## Summary",
        "",
        f"- **State:** {state_emoji} {review_request.get_state_display()}",
        f"- **Requester:** {review_request.requester.username}",
        f"- **Reviewers:** {reviewer_names}",
        f"- **Due date:** {_fmt_dt(review_request.due_date)}",
        f"- **Created:** {_fmt_dt(review_request.created_at)}",
        f"- **Last updated:** {_fmt_dt(review_request.updated_at)}",
        "- **Verdicts:**",
    ]
    lines.extend(_verdict_lines(review_request))
    lines.append("")

    if review_request.description:
        lines.extend(["## Description", "", review_request.description, ""])

    lines.extend(["## Cases under review", ""])
    lines.extend(_cases_table_lines(review_request))

    votes_block = _votes_table_lines(review_request)
    if votes_block:
        lines.extend(votes_block)

    return lines


# ─── Changelog reconstructed from HistoricalRecords ──────────────────


def _history_user(h) -> str:
    u = getattr(h, "history_user", None)
    if u is None:
        return "system"
    return getattr(u, "username", None) or "system"


def _request_history_events(review_request) -> list[dict]:
    """Translate each HistoricalReviewRequest record into a dict for
    chronological merge."""
    events = []
    records = list(review_request.history.order_by("history_date"))
    previous = None
    for h in records:
        if h.history_type == "+":
            events.append({
                "at": h.history_date,
                "actor": _history_user(h),
                "kind": "request_created",
                "detail": None,
            })
        elif h.history_type == "~" and previous is not None:
            if getattr(previous, "state", None) != h.state:
                events.append({
                    "at": h.history_date,
                    "actor": _history_user(h),
                    "kind": "state_changed",
                    "detail": {
                        "from": previous.state,
                        "to": h.state,
                    },
                })
            # description / title / due_date edits could be added here;
            # keep the changelog focused on state for now.
        previous = h
    return events


def _item_history_events(item) -> list[dict]:
    events = []
    previous = None
    case_id = item.case_id
    case_summary = _safe_cell(item.case.summary) if item.case_id else "—"
    for h in item.history.order_by("history_date"):
        if h.history_type == "+":
            events.append({
                "at": h.history_date,
                "actor": _history_user(h),
                "kind": "item_added",
                "detail": {
                    "case_id": case_id,
                    "case_summary": case_summary,
                    "decision": h.decision,
                },
            })
        elif h.history_type == "~" and previous is not None:
            if previous.decision != h.decision or (previous.comment or "") != (h.comment or ""):
                events.append({
                    "at": h.history_date,
                    "actor": _history_user(h),
                    "kind": "item_decision",
                    "detail": {
                        "case_id": case_id,
                        "case_summary": case_summary,
                        "from": previous.decision,
                        "to": h.decision,
                        "comment": h.comment or "",
                    },
                })
        previous = h
    return events


def _vote_history_events(vote) -> list[dict]:
    events = []
    previous = None
    reviewer_name = vote.reviewer.username if vote.reviewer_id else "—"
    for h in vote.history.order_by("history_date"):
        if h.history_type == "+":
            events.append({
                "at": h.history_date,
                "actor": reviewer_name,
                "kind": "vote_cast",
                "detail": {
                    "reviewer": reviewer_name,
                    "decision": h.decision,
                    "comment": h.comment or "",
                },
            })
        elif h.history_type == "~" and previous is not None:
            if previous.decision != h.decision or (previous.comment or "") != (h.comment or ""):
                events.append({
                    "at": h.history_date,
                    "actor": reviewer_name,
                    "kind": "vote_updated",
                    "detail": {
                        "reviewer": reviewer_name,
                        "from": previous.decision,
                        "to": h.decision,
                        "comment": h.comment or "",
                    },
                })
        previous = h
    return events


def _humanise(decision: str) -> str:
    return (decision or "pending").replace("_", " ").title()


def _render_event(event: dict) -> list[str]:
    stamp = event["at"].strftime("%Y-%m-%d %H:%M")
    actor = event["actor"]
    detail = event.get("detail") or {}

    if event["kind"] == "request_created":
        return [
            "",
            f"## 🆕 [{stamp}] Review created by {actor}",
            "",
        ]

    if event["kind"] == "state_changed":
        to_emoji = _STATE_EMOJI.get(detail["to"], "")
        return [
            "",
            f"## 🔁 [{stamp}] State: {_humanise(detail['from'])} → "
            f"{to_emoji} {_humanise(detail['to'])}",
            "",
            f"- **By:** {actor}",
            "",
        ]

    if event["kind"] == "item_added":
        emoji = _DECISION_EMOJI.get(detail["decision"], "")
        return [
            "",
            f"## ➕ [{stamp}] Case TC-{detail['case_id']} attached",
            "",
            f"- **Case:** TC-{detail['case_id']} — {detail['case_summary']}",
            f"- **By:** {actor}",
            f"- **Initial decision:** {emoji} {_humanise(detail['decision'])}",
            "",
        ]

    if event["kind"] == "item_decision":
        from_emoji = _DECISION_EMOJI.get(detail["from"], "")
        to_emoji = _DECISION_EMOJI.get(detail["to"], "")
        lines = [
            "",
            f"## 📝 [{stamp}] Case TC-{detail['case_id']}: "
            f"{from_emoji} {_humanise(detail['from'])} → "
            f"{to_emoji} {_humanise(detail['to'])}",
            "",
            f"- **Case:** TC-{detail['case_id']} — {detail['case_summary']}",
            f"- **By:** {actor}",
        ]
        if detail.get("comment"):
            lines.extend([
                "- **Comment:**",
                "",
                f"> {detail['comment'].replace(chr(10), chr(10) + '> ')}",
            ])
        lines.append("")
        return lines

    if event["kind"] == "vote_cast":
        emoji = _DECISION_EMOJI.get(detail["decision"], "")
        lines = [
            "",
            f"## 🗳️ [{stamp}] Vote cast by {detail['reviewer']}: "
            f"{emoji} {_humanise(detail['decision'])}",
            "",
        ]
        if detail.get("comment"):
            lines.extend([
                "- **Comment:**",
                "",
                f"> {detail['comment'].replace(chr(10), chr(10) + '> ')}",
            ])
        lines.append("")
        return lines

    if event["kind"] == "vote_updated":
        from_emoji = _DECISION_EMOJI.get(detail["from"], "")
        to_emoji = _DECISION_EMOJI.get(detail["to"], "")
        lines = [
            "",
            f"## 🔁 [{stamp}] Vote updated by {detail['reviewer']}: "
            f"{from_emoji} {_humanise(detail['from'])} → "
            f"{to_emoji} {_humanise(detail['to'])}",
            "",
        ]
        if detail.get("comment"):
            lines.extend([
                "- **Comment:**",
                "",
                f"> {detail['comment'].replace(chr(10), chr(10) + '> ')}",
            ])
        lines.append("")
        return lines

    return []


def _build_changelog_section(review_request) -> list[str]:
    """Merge all history records across request + items + votes into
    one chronological changelog."""
    events: list[dict] = []
    events.extend(_request_history_events(review_request))

    for item in review_request.items.select_related("case").all():
        events.extend(_item_history_events(item))

    for vote in review_request.votes.select_related("reviewer").all():
        events.extend(_vote_history_events(vote))

    events.sort(key=lambda e: e["at"])

    lines = [
        "---",
        "",
        "## Activity log",
        "",
        "_Chronological — oldest at the top, newest at the bottom. "
        "Synced automatically by kiwitcms-review._",
    ]
    if not events:
        lines.extend(["", "_No changes logged yet._", ""])
        return lines

    for event in events:
        lines.extend(_render_event(event))

    return lines


# ─── Public API ──────────────────────────────────────────────────────


def build_full_body(review_request) -> str:
    """Generate the complete wiki page body from the current DB state.

    Always reconstructs the full page — every sync writes this with
    `append=False`, so the top section and the changelog are always
    accurate reflections of reality.
    """
    lines = _build_top_section(review_request)
    lines.extend(_build_changelog_section(review_request))
    return "\n".join(lines)


# Back-compat aliases — older signal-handler call sites still reference
# these. All of them now return the full rebuilt body; the caller must
# pass append=False to the adapter.
def build_create_body(review_request) -> str:
    return build_full_body(review_request)


def build_update_body(review_request, previous_state="", event="update", actor="system") -> str:
    return build_full_body(review_request)


def build_item_decision_body(item, previous_decision="", actor="system") -> str:
    return build_full_body(item.review_request)


def build_vote_cast_body(vote, previous_decision="", actor="system") -> str:
    return build_full_body(vote.review_request)
