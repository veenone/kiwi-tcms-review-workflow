from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect, JsonResponse
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
from tcms_review.state_machine import State

_PENDING_LIMIT = 10


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.view_reviewrequest"), name="dispatch")
class List(ListView):
    model = ReviewRequest
    template_name = "tcms_review/list.html"
    context_object_name = "review_requests"
    paginate_by = 25

    def get_queryset(self):
        qs = ReviewRequest.objects.select_related("requester").prefetch_related("reviewers")
        state = self.request.GET.get("state")
        if state:
            qs = qs.filter(state=state)
        if self.request.GET.get("mine_only"):
            qs = qs.filter(reviewers=self.request.user)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["state_choices"] = State.CHOICES
        ctx["selected_state"] = self.request.GET.get("state", "")
        ctx["mine_only"] = bool(self.request.GET.get("mine_only"))
        return ctx


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.add_reviewrequest"), name="dispatch")
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
@method_decorator(permission_required("tcms_review.view_reviewrequest"), name="dispatch")
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
        ctx["metrics"] = reports.metrics(self.object)
        return ctx


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.change_reviewrequest"), name="dispatch")
class Edit(UpdateView):
    model = ReviewRequest
    form_class = NewReviewRequestForm
    template_name = "tcms_review/mutable.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.change_reviewrequest"), name="dispatch")
class Cancel(View):
    def post(self, request, pk):
        review_request = get_object_or_404(ReviewRequest, pk=pk)
        if review_request.requester_id != request.user.pk:
            raise PermissionDenied("Only the requester can cancel a review request.")
        if review_request.state != State.CANCELLED:
            review_request.state = State.CANCELLED
            review_request.save(update_fields=["state", "updated_at"])
        return HttpResponseRedirect(review_request.get_absolute_url())


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.change_reviewrequest"), name="dispatch")
class Vote(View):
    def post(self, request, pk):
        review_request = get_object_or_404(ReviewRequest, pk=pk)
        if not review_request.reviewers.filter(pk=request.user.pk).exists():
            raise PermissionDenied("Only assigned reviewers can vote on this request.")
        if review_request.state == State.CANCELLED:
            raise PermissionDenied("Cannot vote on a cancelled review request.")

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
@method_decorator(permission_required("tcms_review.change_reviewrequest"), name="dispatch")
class ItemDecision(View):
    def post(self, request, pk):
        item = get_object_or_404(ReviewItem.objects.select_related("review_request"), pk=pk)
        decision = request.POST.get("decision", ReviewItem.PENDING)
        comment = request.POST.get("comment", "")
        valid = {choice for choice, _ in ReviewItem.DECISION_CHOICES}
        if decision not in valid:
            raise PermissionDenied("Invalid decision value.")
        item.decision = decision
        item.comment = comment
        item.save(update_fields=["decision", "comment", "updated_at"])
        return HttpResponseRedirect(item.review_request.get_absolute_url())


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.view_reviewrequest"), name="dispatch")
class Search(TemplateView):
    template_name = "tcms_review/search.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.view_reviewrequest"), name="dispatch")
class Report(DetailView):
    model = ReviewRequest
    template_name = "tcms_review/report.html"
    context_object_name = "review_request"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["metrics"] = reports.metrics(self.object)
        return ctx


# ─── JSON endpoints consumed by the JS injection bundle ──────────────


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.view_reviewrequest"), name="dispatch")
class PendingMineJSON(View):
    """Dashboard widget data source: requests assigned to the current user
    that are still open and haven't received their vote yet."""

    def get(self, request):
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
        return JsonResponse({"results": payload})


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.view_reviewrequest"), name="dispatch")
class CaseLatestJSON(View):
    """Per-case badge data source: latest ReviewItem for a given TestCase."""

    def get(self, request, case_pk):
        item = (
            ReviewItem.objects
            .filter(case_id=case_pk)
            .select_related("review_request")
            .order_by("-updated_at")
            .first()
        )
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
@method_decorator(permission_required("tcms_review.view_reviewrequest"), name="dispatch")
class AllowedStatusesJSON(View):
    """Expose the configured allowed case statuses so the JS 'add case'
    form can warn users when a case's status doesn't qualify."""

    def get(self, request):
        return JsonResponse({"allowed": get_allowed_case_statuses()})


# ─── Statistics dashboard ──────────────────────────────────────────────


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("tcms_review.view_reviewrequest"), name="dispatch")
class Stats(TemplateView):
    """Aggregate review statistics and KPIs across all requests."""

    template_name = "tcms_review/stats.html"

    def get_context_data(self, **kwargs):
        import json  # noqa: WPS433
        from datetime import timedelta  # noqa: WPS433

        from django.db.models import Avg, Count, F, Max, Min  # noqa: WPS433
        from django.utils import timezone  # noqa: WPS433

        ctx = super().get_context_data(**kwargs)

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

        # ── KPIs ──────────────────────────────────────────────────────
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

        # ── Chart payload (embedded as JSON) ──────────────────────────
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

        return ctx
