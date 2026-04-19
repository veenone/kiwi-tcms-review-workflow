"""Pure data-gathering functions for report exports.

Each function returns a plain dict suitable for rendering via DocxRenderer
or PdfRenderer. All Kiwi model imports are lazy so this module can be
loaded without pulling the full tcms.* stack at startup.
"""
from datetime import datetime

from django.utils import timezone


def _serialize_request(review_request):
    return {
        "id": review_request.pk,
        "title": review_request.title,
        "description": review_request.description or "",
        "state": review_request.state,
        "state_display": review_request.get_state_display(),
        "requester": review_request.requester.username,
        "due_date": review_request.due_date,
        "created_at": review_request.created_at,
        "updated_at": review_request.updated_at,
        "reviewers": [u.username for u in review_request.reviewers.all()],
    }


def _serialize_items(review_request):
    rows = []
    for item in review_request.items.select_related("case").all():
        rows.append({
            "case_id": item.case_id,
            "summary": item.case.summary,
            "decision": item.decision,
            "decision_display": item.get_decision_display(),
            "comment": item.comment or "",
        })
    return rows


def _serialize_votes(review_request):
    rows = []
    for vote in review_request.votes.select_related("reviewer").all():
        rows.append({
            "reviewer": vote.reviewer.username,
            "decision": vote.decision,
            "decision_display": vote.get_decision_display(),
            "comment": vote.comment or "",
            "voted_at": vote.voted_at,
        })
    return rows


def single_review(review_pk):
    """Data for a single review's full report."""
    from tcms_review.models import ReviewRequest  # noqa: WPS433
    from tcms_review import reports  # noqa: WPS433

    review = (
        ReviewRequest.objects
        .select_related("requester")
        .prefetch_related("reviewers", "items", "items__case", "votes", "votes__reviewer")
        .get(pk=review_pk)
    )
    return {
        "scope": "single",
        "generated_at": timezone.now(),
        "review": _serialize_request(review),
        "items": _serialize_items(review),
        "votes": _serialize_votes(review),
        "metrics": reports.metrics(review),
    }


def _reviews_for_cases(case_ids, start, end):
    """Return ReviewRequests that include any of the given cases,
    optionally constrained to a creation-date window."""
    from tcms_review.models import ReviewRequest  # noqa: WPS433

    qs = (
        ReviewRequest.objects
        .filter(cases__in=case_ids)
        .distinct()
        .select_related("requester")
        .prefetch_related("reviewers", "items__case", "votes__reviewer")
        .order_by("-created_at")
    )
    if start:
        qs = qs.filter(created_at__gte=start)
    if end:
        qs = qs.filter(created_at__lte=end)
    return qs


def _summary_by_state(reviews):
    counts = {}
    for r in reviews:
        counts[r["state_display"]] = counts.get(r["state_display"], 0) + 1
    return counts


def consolidated_by_product(product_pk, start=None, end=None):
    """Every review whose cases belong to the given Kiwi Product."""
    from tcms.management.models import Product  # noqa: WPS433
    from tcms.testcases.models import TestCase  # noqa: WPS433

    product = Product.objects.get(pk=product_pk)
    case_ids = list(
        TestCase.objects
        .filter(category__product=product)
        .values_list("pk", flat=True)
    )

    reviews_qs = _reviews_for_cases(case_ids, start, end)
    serialised = []
    for review in reviews_qs:
        serialised.append({
            **_serialize_request(review),
            "items": _serialize_items(review),
            "votes": _serialize_votes(review),
        })

    return {
        "scope": "product",
        "generated_at": timezone.now(),
        "title": f"Review report — Product: {product.name}",
        "scope_entity": {"kind": "product", "id": product.pk, "name": product.name},
        "date_range": {"start": start, "end": end},
        "reviews": serialised,
        "summary": {
            "total_reviews": len(serialised),
            "total_cases": len(case_ids),
            "by_state": _summary_by_state(serialised),
        },
    }


def consolidated_by_testplan(testplan_pk, start=None, end=None):
    """Every review whose cases belong to the given TestPlan."""
    from tcms.testplans.models import TestPlan  # noqa: WPS433

    plan = TestPlan.objects.get(pk=testplan_pk)
    case_ids = list(plan.cases.values_list("pk", flat=True))

    reviews_qs = _reviews_for_cases(case_ids, start, end)
    serialised = []
    for review in reviews_qs:
        serialised.append({
            **_serialize_request(review),
            "items": _serialize_items(review),
            "votes": _serialize_votes(review),
        })

    return {
        "scope": "testplan",
        "generated_at": timezone.now(),
        "title": f"Review report — TestPlan TP-{plan.pk}: {plan.name}",
        "scope_entity": {"kind": "testplan", "id": plan.pk, "name": plan.name},
        "date_range": {"start": start, "end": end},
        "reviews": serialised,
        "summary": {
            "total_reviews": len(serialised),
            "total_cases": len(case_ids),
            "by_state": _summary_by_state(serialised),
        },
    }


def consolidated_by_testrun(testrun_pk, start=None, end=None):
    """Every review whose cases appear in executions of the given TestRun."""
    from tcms.testruns.models import TestRun  # noqa: WPS433

    run = TestRun.objects.select_related("plan").get(pk=testrun_pk)
    case_ids = list(
        run.executions.values_list("case_id", flat=True).distinct()
    )

    reviews_qs = _reviews_for_cases(case_ids, start, end)
    serialised = []
    for review in reviews_qs:
        serialised.append({
            **_serialize_request(review),
            "items": _serialize_items(review),
            "votes": _serialize_votes(review),
        })

    return {
        "scope": "testrun",
        "generated_at": timezone.now(),
        "title": f"Review report — TestRun TR-{run.pk}: {run.summary}",
        "scope_entity": {"kind": "testrun", "id": run.pk, "name": run.summary},
        "date_range": {"start": start, "end": end},
        "reviews": serialised,
        "summary": {
            "total_reviews": len(serialised),
            "total_cases": len(case_ids),
            "by_state": _summary_by_state(serialised),
        },
    }


def export_filename(scope, entity_id, fmt):
    """Build a consistent filename for download attachments."""
    stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    return f"review-{scope}-{entity_id}-{stamp}.{fmt}"
