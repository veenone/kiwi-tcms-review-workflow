from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
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
from tcms_review.forms import NewReviewRequestForm, VoteForm
from tcms_review.models import ReviewItem, ReviewRequest, ReviewVote
from tcms_review.state_machine import State


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
            ReviewItem.objects.get_or_create(
                review_request=self.object,
                case_id=case_pk,
            )
        return response


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
