"""XML-RPC / JSON-RPC methods for the review workflow.

Auto-discovered by modernrpc once apps.py::ready() appends this module
to MODERNRPC_METHODS_MODULES. Every method mirrors the decorator stack
used by tcms/bugs/api.py:

    @permissions_required("tcms_review.<codename>")
    @rpc_method(name="ReviewRequest.<method>")
    def method(...):
        ...

Input is validated via the same Django forms the HTML UI uses, so RPC
clients get the same error shapes. Permission errors raise
PermissionDenied; validation errors raise ValueError.
"""
from django.core.exceptions import PermissionDenied
from django.forms.models import model_to_dict
from modernrpc.core import REQUEST_KEY, rpc_method

from tcms.rpc.decorators import permissions_required

from tcms_review import reports
from tcms_review.forms import NewReviewRequestForm, VoteForm
from tcms_review.models import ReviewItem, ReviewRequest, ReviewVote
from tcms_review.state_machine import State, VoteDecision


def _serialize_request(obj):
    return {
        "id": obj.pk,
        "title": obj.title,
        "description": obj.description,
        "state": obj.state,
        "due_date": obj.due_date.isoformat() if obj.due_date else None,
        "requester": obj.requester_id,
        "requester__username": obj.requester.username,
        "created_at": obj.created_at.isoformat(),
        "updated_at": obj.updated_at.isoformat(),
    }


def _serialize_vote(obj):
    return {
        "id": obj.pk,
        "review_request": obj.review_request_id,
        "reviewer": obj.reviewer_id,
        "reviewer__username": obj.reviewer.username,
        "decision": obj.decision,
        "comment": obj.comment,
        "voted_at": obj.voted_at.isoformat(),
    }


def _serialize_item(obj):
    return {
        "id": obj.pk,
        "review_request": obj.review_request_id,
        "case": obj.case_id,
        "decision": obj.decision,
        "comment": obj.comment,
        "updated_at": obj.updated_at.isoformat(),
    }


def _metrics_dict(review_request):
    raw = reports.metrics(review_request)
    ttd = raw["time_to_decision"]
    return {
        "state": raw["state"],
        "votes": raw["votes"],
        "items": raw["items"],
        "participation": raw["participation"],
        "time_to_decision_seconds": int(ttd.total_seconds()) if ttd else None,
    }


# ─── ReviewRequest ────────────────────────────────────────────────────────


@permissions_required("tcms_review.add_reviewrequest")
@rpc_method(name="ReviewRequest.create")
def create(values, **kwargs):
    """Create a new review request.

    `values` is a dict validated through NewReviewRequestForm plus an
    optional `cases` list of TestCase IDs. The calling user becomes the
    requester.
    """
    cases = values.pop("cases", []) if isinstance(values, dict) else []
    form = NewReviewRequestForm(data=values)
    if not form.is_valid():
        raise ValueError(form.errors.as_json())

    request_user = kwargs.get(REQUEST_KEY).user
    review_request = form.save(commit=False)
    review_request.requester = request_user
    review_request.save()
    form.save_m2m()

    for case_pk in cases:
        ReviewItem.objects.get_or_create(
            review_request=review_request, case_id=case_pk,
        )

    return _serialize_request(review_request)


@permissions_required("tcms_review.view_reviewrequest")
@rpc_method(name="ReviewRequest.filter")
def filter_requests(query=None):
    qs = (
        ReviewRequest.objects
        .filter(**(query or {}))
        .select_related("requester")
    )
    return [_serialize_request(r) for r in qs]


@permissions_required("tcms_review.view_reviewrequest")
@rpc_method(name="ReviewRequest.filter_canonical")
def filter_canonical(query=None):
    """Return matching review request IDs only. Mirrors Bug.filter_canonical."""
    return list(
        ReviewRequest.objects.filter(**(query or {})).values_list("pk", flat=True)
    )


@permissions_required("tcms_review.change_reviewrequest")
@rpc_method(name="ReviewRequest.add_case")
def add_case(request_id, case_id):
    from tcms.testcases.models import TestCase  # noqa: WPS433
    from tcms_review.conf import get_allowed_case_statuses  # noqa: WPS433

    case = TestCase.objects.select_related("case_status").get(pk=case_id)
    allowed = get_allowed_case_statuses()
    if case.case_status.name.upper() not in [s.upper() for s in allowed]:
        raise ValueError(
            f"TestCase status '{case.case_status.name}' is not allowed for "
            f"review. Allowed statuses: {', '.join(allowed)}"
        )

    review_request = ReviewRequest.objects.get(pk=request_id)
    item, _ = ReviewItem.objects.get_or_create(
        review_request=review_request, case_id=case.pk,
    )
    return _serialize_item(item)


@permissions_required("tcms_review.change_reviewrequest")
@rpc_method(name="ReviewRequest.remove_case")
def remove_case(request_id, case_id):
    ReviewItem.objects.filter(
        review_request_id=request_id, case_id=case_id,
    ).delete()
    return True


@permissions_required("tcms_review.change_reviewrequest")
@rpc_method(name="ReviewRequest.add_reviewer")
def add_reviewer(request_id, user_id):
    review_request = ReviewRequest.objects.get(pk=request_id)
    review_request.reviewers.add(user_id)
    return True


@permissions_required("tcms_review.change_reviewrequest")
@rpc_method(name="ReviewRequest.remove_reviewer")
def remove_reviewer(request_id, user_id):
    review_request = ReviewRequest.objects.get(pk=request_id)
    review_request.reviewers.remove(user_id)
    review_request.recalculate_state()
    return True


@permissions_required("tcms_review.change_reviewrequest")
@rpc_method(name="ReviewRequest.cancel")
def cancel(request_id, **kwargs):
    """Only the requester can cancel."""
    review_request = ReviewRequest.objects.get(pk=request_id)
    request_user = kwargs.get(REQUEST_KEY).user
    if review_request.requester_id != request_user.pk:
        raise PermissionDenied("Only the requester can cancel a review request.")
    if review_request.state != State.CANCELLED:
        review_request.state = State.CANCELLED
        review_request.save(update_fields=["state", "updated_at"])
    return _serialize_request(review_request)


@permissions_required("tcms_review.view_reviewrequest")
@rpc_method(name="ReviewRequest.metrics")
def metrics(request_id):
    review_request = ReviewRequest.objects.get(pk=request_id)
    return _metrics_dict(review_request)


# ─── ReviewVote ───────────────────────────────────────────────────────────


@permissions_required("tcms_review.change_reviewrequest")
@rpc_method(name="ReviewVote.cast")
def cast_vote(request_id, decision, comment="", **kwargs):
    """Cast (or revise) the current user's vote on a review request."""
    review_request = ReviewRequest.objects.get(pk=request_id)
    request_user = kwargs.get(REQUEST_KEY).user

    if not review_request.reviewers.filter(pk=request_user.pk).exists():
        raise PermissionDenied("Only assigned reviewers can vote on this request.")
    if review_request.state == State.CANCELLED:
        raise PermissionDenied("Cannot vote on a cancelled review request.")

    form = VoteForm(data={"decision": decision, "comment": comment})
    if not form.is_valid():
        raise ValueError(form.errors.as_json())

    vote, _ = ReviewVote.objects.update_or_create(
        review_request=review_request,
        reviewer=request_user,
        defaults={
            "decision": form.cleaned_data["decision"],
            "comment": form.cleaned_data.get("comment", ""),
        },
    )
    return _serialize_vote(vote)


@permissions_required("tcms_review.view_reviewrequest")
@rpc_method(name="ReviewVote.filter")
def filter_votes(query=None):
    qs = (
        ReviewVote.objects
        .filter(**(query or {}))
        .select_related("reviewer")
    )
    return [_serialize_vote(v) for v in qs]


# ─── ReviewItem ───────────────────────────────────────────────────────────


@permissions_required("tcms_review.change_reviewrequest")
@rpc_method(name="ReviewItem.set_decision")
def set_item_decision(item_id, decision, comment=""):
    valid = {choice for choice, _ in ReviewItem.DECISION_CHOICES}
    if decision not in valid:
        raise ValueError(f"Invalid decision: {decision}")
    item = ReviewItem.objects.get(pk=item_id)
    item.decision = decision
    item.comment = comment
    item.save(update_fields=["decision", "comment", "updated_at"])
    return _serialize_item(item)


@permissions_required("tcms_review.view_reviewrequest")
@rpc_method(name="ReviewItem.filter")
def filter_items(query=None):
    """Return items matching `query`. Used by the JS injection bundle
    to render per-case status badges on TestCase detail pages.
    """
    qs = (
        ReviewItem.objects
        .filter(**(query or {}))
        .select_related("review_request")
        .order_by("-updated_at")
    )
    return [_serialize_item(i) for i in qs]
