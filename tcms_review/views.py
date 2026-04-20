from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db.utils import DatabaseError
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)

from tcms_review import reports
from tcms_review.conf import get_allowed_case_statuses
from tcms_review.forms import NewReviewRequestForm, VoteForm
from tcms_review.models import ReviewItem, ReviewRequest, ReviewVote
from tcms_review.state_machine import State, VoteDecision

_PENDING_LIMIT = 10


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.view_reviewrequest", raise_exception=True), name="dispatch")
class List(ListView):
    model = ReviewRequest
    template_name = "tcms_review/list.html"
    context_object_name = "review_requests"
    paginate_by = 25

    def get_queryset(self):
        try:
            qs = ReviewRequest.objects.select_related("requester").prefetch_related("reviewers")
            state = self.request.GET.get("state")
            if state:
                qs = qs.filter(state=state)
            if self.request.GET.get("mine_only"):
                qs = qs.filter(reviewers=self.request.user)
            # Force evaluation so a missing table raises here, caught below,
            # rather than during template rendering where it would 500.
            list(qs[:0])
            return qs
        except DatabaseError:
            self._db_unavailable = True
            return ReviewRequest.objects.none()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["state_choices"] = State.CHOICES
        ctx["selected_state"] = self.request.GET.get("state", "")
        ctx["mine_only"] = bool(self.request.GET.get("mine_only"))
        ctx["db_unavailable"] = getattr(self, "_db_unavailable", False)
        return ctx


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.add_reviewrequest", raise_exception=True), name="dispatch")
class New(CreateView):
    model = ReviewRequest
    form_class = NewReviewRequestForm
    template_name = "tcms_review/mutable.html"

    def form_valid(self, form):
        form.instance.requester = self.request.user
        response = super().form_valid(form)

        case_pk = self.request.GET.get("testcase")
        if case_pk:
            self._attach_case(case_pk)
        return response

    def _attach_case(self, case_pk):
        from tcms.testcases.models import TestCase  # noqa: WPS433

        try:
            case = TestCase.objects.select_related("case_status").get(pk=case_pk)
        except TestCase.DoesNotExist:
            return

        allowed = get_allowed_case_statuses()
        if case.case_status.name.upper() not in [s.upper() for s in allowed]:
            return

        ReviewItem.objects.get_or_create(
            review_request=self.object,
            case_id=case.pk,
        )


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.view_reviewrequest", raise_exception=True), name="dispatch")
class Get(DetailView):
    model = ReviewRequest
    template_name = "tcms_review/get.html"
    context_object_name = "review_request"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["votes"] = self.object.votes.select_related("reviewer")
        ctx["items"] = self.object.items.select_related("case")
        ctx["vote_form"] = VoteForm()
        ctx["is_reviewer"] = self.object.reviewers.filter(pk=self.request.user.pk).exists()
        ctx["is_owner"] = self.object.requester_id == self.request.user.pk
        ctx["is_locked"] = self.object.is_locked
        ctx["has_pending_items"] = self.object.has_pending_items
        ctx["can_vote"] = (
            ctx["is_reviewer"]
            and not ctx["is_locked"]
            and self.object.state != State.CANCELLED
            and not ctx["has_pending_items"]
        )
        ctx["metrics"] = reports.metrics(self.object)
        ctx["activity"] = _build_activity_feed(self.object)
        return ctx


@method_decorator(login_required, name="dispatch")
class Edit(UpdateView):
    """Edit a review request — title, description, due date, reviewers.

    Access rule: the requester (author) can always edit their own
    request; otherwise the user needs the ``tcms_review.change_reviewrequest``
    permission. This lets a tester who created a request adjust
    description / reviewers without needing the blanket change permission.
    Approved (locked) requests are immutable regardless.
    """

    model = ReviewRequest
    form_class = NewReviewRequestForm
    template_name = "tcms_review/mutable.html"

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.is_locked:
            raise PermissionDenied(
                "This review request is approved and can no longer be modified."
            )
        is_owner = obj.requester_id == request.user.pk
        has_change = request.user.has_perm("tcms_review.change_reviewrequest")
        if not (is_owner or has_change):
            raise PermissionDenied(
                "Only the requester or a user with change permission "
                "can edit this review request."
            )
        return super().dispatch(request, *args, **kwargs)


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.change_reviewrequest", raise_exception=True), name="dispatch")
class Cancel(View):
    def post(self, request, pk):
        review_request = get_object_or_404(ReviewRequest, pk=pk)
        if review_request.is_locked:
            raise PermissionDenied("Approved review requests cannot be cancelled.")
        if review_request.requester_id != request.user.pk:
            raise PermissionDenied("Only the requester can cancel a review request.")
        if review_request.state != State.CANCELLED:
            review_request.state = State.CANCELLED
            review_request.save(update_fields=["state", "updated_at"])
        return HttpResponseRedirect(review_request.get_absolute_url())


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.change_reviewrequest", raise_exception=True), name="dispatch")
class Vote(View):
    def post(self, request, pk):
        review_request = get_object_or_404(ReviewRequest, pk=pk)
        if review_request.is_locked:
            raise PermissionDenied("This review request is approved and can no longer be voted on.")
        if not review_request.reviewers.filter(pk=request.user.pk).exists():
            raise PermissionDenied("Only assigned reviewers can vote on this request.")
        if review_request.state == State.CANCELLED:
            raise PermissionDenied("Cannot vote on a cancelled review request.")
        if review_request.has_pending_items:
            raise PermissionDenied(
                "All cases must have a decision recorded before you can cast your vote."
            )

        form = VoteForm(request.POST)
        if not form.is_valid():
            return HttpResponseRedirect(review_request.get_absolute_url())

        ReviewVote.objects.update_or_create(
            review_request=review_request,
            reviewer=request.user,
            defaults={
                "decision": form.cleaned_data["decision"],
                "comment": form.cleaned_data.get("comment", ""),
            },
        )
        return HttpResponseRedirect(review_request.get_absolute_url())


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.change_reviewrequest", raise_exception=True), name="dispatch")
class ResubmitItem(View):
    """Tester-driven resubmission of a case that was previously marked
    needs_changes or rejected. Resets the item's decision to pending,
    which — via the existing status-transition signal — also flips the
    TestCase status back to PROPOSED (if the NEED_UPDATE/DISABLED rule
    is configured)."""

    def post(self, request, pk):
        item = get_object_or_404(ReviewItem.objects.select_related("review_request"), pk=pk)
        review_request = item.review_request

        if review_request.is_locked:
            raise PermissionDenied("This review request is approved and can no longer be modified.")
        if review_request.state == State.CANCELLED:
            raise PermissionDenied("This review request has been cancelled and cannot be reopened.")
        if item.decision not in (VoteDecision.NEEDS_CHANGES, VoteDecision.REJECTED):
            raise PermissionDenied(
                "Only cases marked 'Needs changes' or 'Rejected' can be resubmitted for re-review."
            )

        item.decision = ReviewItem.PENDING
        item.comment = ""
        item.save(update_fields=["decision", "comment", "updated_at"])
        return HttpResponseRedirect(review_request.get_absolute_url())


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.change_reviewrequest", raise_exception=True), name="dispatch")
class ItemDecision(View):
    def post(self, request, pk):
        item = get_object_or_404(ReviewItem.objects.select_related("review_request"), pk=pk)
        if item.review_request.is_locked:
            raise PermissionDenied("This review request is approved and can no longer be modified.")
        decision = request.POST.get("decision", ReviewItem.PENDING)
        comment = request.POST.get("comment", "")
        valid = {choice for choice, _ in ReviewItem.DECISION_CHOICES}
        if decision not in valid:
            raise PermissionDenied("Invalid decision value.")
        item.decision = decision
        item.comment = comment
        item.save(update_fields=["decision", "comment", "updated_at"])
        return HttpResponseRedirect(item.review_request.get_absolute_url())


def _build_activity_feed(review_request):
    """Derive a threaded audit trail from the three HistoricalRecords managers.

    Returns a list of threads, each thread is:
        {kind: 'request'|'item'|'vote', title: str, entries: [entry, ...]}
    Entries within a thread are ordered oldest-first (natural reading order).
    Threads are ordered by the oldest entry's timestamp so the request
    thread sits at the top and conversational threads (per-case, per-vote)
    appear in the order they were opened.

    Each entry captures:
        {timestamp, user, label, detail, comment_before, comment_after, state_before, state_after}

    No new model or migration required — django-simple-history is already
    tracking everything we need on the three plugin models.
    """
    threads = []

    # Request thread — top-level
    request_entries = []
    prev = None
    for h in review_request.history.order_by("history_date"):
        entry = _make_entry(
            h, kind="request",
            label=_history_label(h),
            detail=f"{h.title}",
            prev=prev,
            compare_fields=["state", "title", "description", "due_date"],
        )
        request_entries.append(entry)
        prev = h
    if request_entries:
        threads.append({
            "kind": "request",
            "title": f"Review request #{review_request.pk}",
            "icon": "fa fa-flag",
            "entries": request_entries,
            "opened_at": request_entries[0]["timestamp"],
        })

    # One thread per ReviewItem
    for item in review_request.items.select_related("case").all():
        item_entries = []
        prev = None
        for h in item.history.order_by("history_date"):
            entry = _make_entry(
                h, kind="item",
                label=_history_label(h, for_decision=True),
                detail=h.get_decision_display(),
                prev=prev,
                compare_fields=["decision", "comment"],
            )
            item_entries.append(entry)
            prev = h
        if item_entries:
            threads.append({
                "kind": "item",
                "title": f"Case #{item.case_id}: {item.case.summary}",
                "icon": "fa fa-file-text-o",
                "entries": item_entries,
                "opened_at": item_entries[0]["timestamp"],
            })

    # One thread per reviewer (their ReviewVote history)
    for vote in review_request.votes.select_related("reviewer").all():
        vote_entries = []
        prev = None
        for h in vote.history.order_by("history_date"):
            entry = _make_entry(
                h, kind="vote",
                label=_history_label(h, for_vote=True),
                detail=h.get_decision_display(),
                prev=prev,
                compare_fields=["decision", "comment"],
            )
            vote_entries.append(entry)
            prev = h
        if vote_entries:
            threads.append({
                "kind": "vote",
                "title": f"Vote by {vote.reviewer.username}",
                "icon": "fa fa-gavel",
                "entries": vote_entries,
                "opened_at": vote_entries[0]["timestamp"],
            })

    threads.sort(key=lambda t: t["opened_at"])

    # Split each thread's entries into a visible tail (last 5) and a hidden
    # older section, so the template can offer a "Show older" reveal
    # without dumping 50 entries at once. Thread-level pagination (5
    # threads per page) is handled client-side in inject.js.
    tail = 5
    for thread in threads:
        entries = thread["entries"]
        if len(entries) > tail:
            thread["hidden_entries"] = entries[:-tail]
            thread["visible_entries"] = entries[-tail:]
        else:
            thread["hidden_entries"] = []
            thread["visible_entries"] = entries

    return threads


def _make_entry(hist_record, kind, label, detail, prev, compare_fields):
    """Assemble a single activity entry with a diff against the prior record."""
    changes = []
    if prev is not None:
        for field in compare_fields:
            old = getattr(prev, field, None)
            new = getattr(hist_record, field, None)
            if old != new:
                changes.append({
                    "field": field,
                    "before": _format_field_value(old),
                    "after": _format_field_value(new),
                })

    return {
        "timestamp": hist_record.history_date,
        "user": hist_record.history_user,
        "kind": kind,
        "label": label,
        "detail": detail,
        "changes": changes,
        "history_type": hist_record.history_type,
    }


def _format_field_value(value):
    if value is None:
        return "—"
    return str(value)


def _history_label(hist_record, for_decision=False, for_vote=False):
    t = hist_record.history_type
    if for_decision:
        if t == "+":
            return "Case added"
        if t == "-":
            return "Case removed"
        return "Case decision updated"
    if for_vote:
        if t == "+":
            return "Vote cast"
        return "Vote updated"
    if t == "+":
        return "Review request created"
    if t == "-":
        return "Review request deleted"
    return "Review request updated"


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.view_reviewrequest", raise_exception=True), name="dispatch")
class Search(TemplateView):
    template_name = "tcms_review/search.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.view_reviewrequest", raise_exception=True), name="dispatch")
class Report(DetailView):
    model = ReviewRequest
    template_name = "tcms_review/report.html"
    context_object_name = "review_request"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["metrics"] = reports.metrics(self.object)
        ctx["activity"] = _build_activity_feed(self.object)
        return ctx


# ─── JSON endpoints consumed by the JS injection bundle ──────────────


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.view_reviewrequest", raise_exception=True), name="dispatch")
class PendingMineJSON(View):
    """Dashboard widget data source: requests assigned to the current user
    that are still open and haven't received their vote yet."""

    def get(self, request):
        try:
            qs = (
                ReviewRequest.objects
                .filter(reviewers=request.user, state=State.IN_REVIEW)
                .exclude(votes__reviewer=request.user)
                .select_related("requester")
                .order_by("due_date")[:_PENDING_LIMIT]
            )
            payload = [
                {
                    "id": r.pk,
                    "title": r.title,
                    "url": reverse("review-get", args=[r.pk]),
                    "requester": r.requester.username,
                    "due_date": r.due_date.isoformat() if r.due_date else None,
                }
                for r in qs
            ]
        except DatabaseError:
            return JsonResponse({"results": []})
        return JsonResponse({"results": payload})


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.view_reviewrequest", raise_exception=True), name="dispatch")
class CaseLatestJSON(View):
    """Per-case badge data source: latest ReviewItem for a given TestCase."""

    def get(self, request, case_pk):
        try:
            item = (
                ReviewItem.objects
                .filter(case_id=case_pk)
                .select_related("review_request")
                .order_by("-updated_at")
                .first()
            )
        except DatabaseError:
            return JsonResponse({"item": None})
        if item is None:
            return JsonResponse({"item": None})
        r = item.review_request
        return JsonResponse({
            "item": {
                "id": item.pk,
                "decision": item.decision,
                "decision_display": item.get_decision_display(),
                "review_request": {
                    "id": r.pk,
                    "title": r.title,
                    "state": r.state,
                    "state_display": r.get_state_display(),
                    "url": reverse("review-get", args=[r.pk]),
                },
            },
        })


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.view_reviewrequest", raise_exception=True), name="dispatch")
class AllowedStatusesJSON(View):
    """Expose the configured allowed case statuses so the JS 'add case'
    form can warn users when a case's status doesn't qualify."""

    def get(self, request):
        try:
            allowed = get_allowed_case_statuses()
        except DatabaseError:
            allowed = []
        return JsonResponse({"allowed": allowed})


# ─── Statistics dashboard ──────────────────────────────────────────────


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.view_reviewrequest", raise_exception=True), name="dispatch")
class Stats(TemplateView):
    """Aggregate review statistics and KPIs across all requests."""

    template_name = "tcms_review/stats.html"

    def get_context_data(self, **kwargs):
        import json  # noqa: WPS433
        from datetime import timedelta  # noqa: WPS433

        from django.db.models import Avg, Count, F, Max, Min  # noqa: WPS433
        from django.utils import timezone  # noqa: WPS433

        ctx = super().get_context_data(**kwargs)
        ctx["db_unavailable"] = False

        try:
            qs = ReviewRequest.objects.all()
            ctx["total_requests"] = qs.count()

            by_state = {}
            for value, label in State.CHOICES:
                by_state[label] = qs.filter(state=value).count()
            ctx["by_state"] = by_state

            ctx["total_votes"] = ReviewVote.objects.count()
            ctx["total_items"] = ReviewItem.objects.count()

            terminal_qs = qs.filter(state__in=list(State.TERMINAL))
            avg_duration = terminal_qs.aggregate(
                avg=Avg(F("updated_at") - F("created_at"))
            )["avg"]
            ctx["avg_time_to_decision"] = avg_duration

            top_reviewers_qs = (
                ReviewVote.objects
                .values("reviewer__username")
                .annotate(vote_count=Count("pk"))
                .order_by("-vote_count")[:10]
            )
            top_reviewers = list(top_reviewers_qs)
            ctx["top_reviewers"] = top_reviewers

            top_requesters_qs = (
                ReviewRequest.objects
                .values("requester__username")
                .annotate(request_count=Count("pk"))
                .order_by("-request_count")[:10]
            )
            top_requesters = list(top_requesters_qs)
            ctx["top_requesters"] = top_requesters

            # ── KPIs ──────────────────────────────────────────────────
            now = timezone.now()
            window_30 = now - timedelta(days=30)

            open_qs = qs.filter(state=State.IN_REVIEW)
            ctx["open_requests"] = open_qs.count()
            ctx["overdue_requests"] = open_qs.filter(due_date__lt=now).count()

            ctx["requests_last_30d"] = qs.filter(created_at__gte=window_30).count()
            ctx["closed_last_30d"] = qs.filter(
                state__in=list(State.TERMINAL), updated_at__gte=window_30,
            ).count()
            ctx["votes_last_30d"] = ReviewVote.objects.filter(voted_at__gte=window_30).count()

            approved_count = qs.filter(state=State.APPROVED).count()
            rejected_count = qs.filter(state=State.REJECTED).count()
            closed = approved_count + rejected_count
            ctx["approval_rate"] = (
                (approved_count * 100.0 / closed) if closed else 0.0
            )

            # Median time-to-decision (best effort in Python; small volumes)
            durations = [
                (r.updated_at - r.created_at).total_seconds()
                for r in terminal_qs.only("created_at", "updated_at")
            ]
            if durations:
                durations.sort()
                mid = len(durations) // 2
                if len(durations) % 2 == 0:
                    median_secs = (durations[mid - 1] + durations[mid]) / 2.0
                else:
                    median_secs = durations[mid]
                ctx["median_time_to_decision"] = timedelta(seconds=int(median_secs))
            else:
                ctx["median_time_to_decision"] = None

            fastest = terminal_qs.aggregate(
                m=Min(F("updated_at") - F("created_at"))
            )["m"]
            slowest = terminal_qs.aggregate(
                m=Max(F("updated_at") - F("created_at"))
            )["m"]
            ctx["fastest_decision"] = fastest
            ctx["slowest_decision"] = slowest

            # ── Chart payload (embedded as JSON) ──────────────────────
            reviewers_for_chart = [
                {"name": row["reviewer__username"], "count": row["vote_count"]}
                for row in top_reviewers
            ]
            requesters_for_chart = [
                {"name": row["requester__username"], "count": row["request_count"]}
                for row in top_requesters
            ]

            daily_qs = (
                qs.filter(created_at__gte=window_30)
                .extra(select={"d": "date(created_at)"})
                .values("d")
                .annotate(count=Count("pk"))
                .order_by("d")
            )
            daily = [
                {"date": str(row["d"]), "count": row["count"]}
                for row in daily_qs
            ]

            ctx["chart_payload_json"] = json.dumps({
                "by_state": by_state,
                "top_reviewers": reviewers_for_chart,
                "top_requesters": requesters_for_chart,
                "daily": daily,
            })
        except DatabaseError:
            ctx["db_unavailable"] = True
            ctx["total_requests"] = 0
            ctx["by_state"] = {label: 0 for _, label in State.CHOICES}
            ctx["total_votes"] = 0
            ctx["total_items"] = 0
            ctx["avg_time_to_decision"] = None
            ctx["top_reviewers"] = []
            ctx["top_requesters"] = []
            ctx["open_requests"] = 0
            ctx["overdue_requests"] = 0
            ctx["requests_last_30d"] = 0
            ctx["closed_last_30d"] = 0
            ctx["votes_last_30d"] = 0
            ctx["approval_rate"] = 0.0
            ctx["median_time_to_decision"] = None
            ctx["fastest_decision"] = None
            ctx["slowest_decision"] = None
            ctx["chart_payload_json"] = json.dumps({
                "by_state": ctx["by_state"],
                "top_reviewers": [],
                "top_requesters": [],
                "daily": [],
            })

        return ctx


# ─── Report hub + exports ─────────────────────────────────────────────


_ALLOWED_FORMATS = ("docx", "pdf")

_FORMAT_CONTENT_TYPE = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}


def _render_export(fmt, data, single=False):
    """Dispatch to the right renderer and return an HttpResponse with
    the correct content-type + attachment filename."""
    from tcms_review.exports import data as data_module  # noqa: WPS433

    if fmt not in _ALLOWED_FORMATS:
        raise PermissionDenied("Unsupported export format.")

    if fmt == "docx":
        from tcms_review.exports.docx_renderer import render_single_review, render_consolidated  # noqa: WPS433
    else:
        from tcms_review.exports.pdf_renderer import render_single_review, render_consolidated  # noqa: WPS433

    buf = render_single_review(data) if single else render_consolidated(data)
    if single:
        filename = data_module.export_filename("single", data["review"]["id"], fmt)
    else:
        filename = data_module.export_filename(
            data["scope"], data["scope_entity"]["id"], fmt,
        )

    response = HttpResponse(
        buf.read(),
        content_type=_FORMAT_CONTENT_TYPE[fmt],
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _parse_date(raw):
    """Parse a YYYY-MM-DD query-string value to a tz-aware datetime."""
    if not raw:
        return None
    from django.utils.dateparse import parse_date  # noqa: WPS433
    from django.utils import timezone  # noqa: WPS433
    from datetime import datetime, time  # noqa: WPS433

    d = parse_date(raw)
    if not d:
        return None
    return timezone.make_aware(datetime.combine(d, time.min))


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.view_reviewrequest", raise_exception=True), name="dispatch")
class ExportSingle(View):
    """Download a single review's report as DOCX or PDF."""

    def get(self, request, pk, fmt):
        from tcms_review.exports.data import single_review  # noqa: WPS433

        get_object_or_404(ReviewRequest, pk=pk)  # 404 if missing / bad pk
        data = single_review(pk)
        return _render_export(fmt, data, single=True)


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.view_reviewrequest", raise_exception=True), name="dispatch")
class ExportProduct(View):
    def get(self, request, product_pk, fmt):
        from tcms_review.exports.data import consolidated_by_product  # noqa: WPS433

        start = _parse_date(request.GET.get("start"))
        end = _parse_date(request.GET.get("end"))
        data = consolidated_by_product(product_pk, start=start, end=end)
        return _render_export(fmt, data)


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.view_reviewrequest", raise_exception=True), name="dispatch")
class ExportTestplan(View):
    def get(self, request, plan_pk, fmt):
        from tcms_review.exports.data import consolidated_by_testplan  # noqa: WPS433

        start = _parse_date(request.GET.get("start"))
        end = _parse_date(request.GET.get("end"))
        data = consolidated_by_testplan(plan_pk, start=start, end=end)
        return _render_export(fmt, data)


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.view_reviewrequest", raise_exception=True), name="dispatch")
class ExportTestrun(View):
    def get(self, request, run_pk, fmt):
        from tcms_review.exports.data import consolidated_by_testrun  # noqa: WPS433

        start = _parse_date(request.GET.get("start"))
        end = _parse_date(request.GET.get("end"))
        data = consolidated_by_testrun(run_pk, start=start, end=end)
        return _render_export(fmt, data)


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.view_reviewrequest", raise_exception=True), name="dispatch")
class ReportHub(TemplateView):
    """Landing page for consolidated exports — pick product/plan/run + date range."""

    template_name = "tcms_review/report_hub.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["scope"] = self.request.GET.get("scope", "product")

        # Lazy imports so module load doesn't drag Kiwi models.
        from tcms.management.models import Product  # noqa: WPS433
        from tcms.testplans.models import TestPlan  # noqa: WPS433
        from tcms.testruns.models import TestRun  # noqa: WPS433

        ctx["products"] = Product.objects.order_by("name")[:200]
        ctx["testplans"] = TestPlan.objects.order_by("-pk")[:200]
        ctx["testruns"] = TestRun.objects.select_related("plan").order_by("-pk")[:200]
        return ctx
