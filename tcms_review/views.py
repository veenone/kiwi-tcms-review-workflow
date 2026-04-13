"""View skeletons. Implemented incrementally per the build sequence in the plan."""
from django.contrib.auth.decorators import permission_required
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, DetailView, TemplateView, UpdateView, View

from tcms_review.models import ReviewRequest


@method_decorator(permission_required("tcms_review.view_reviewrequest"), name="dispatch")
class List(TemplateView):
    template_name = "tcms_review/list.html"


@method_decorator(permission_required("tcms_review.add_reviewrequest"), name="dispatch")
class New(CreateView):
    model = ReviewRequest
    template_name = "tcms_review/mutable.html"
    fields = ["title", "description", "due_date", "reviewers"]


@method_decorator(permission_required("tcms_review.view_reviewrequest"), name="dispatch")
class Get(DetailView):
    model = ReviewRequest
    template_name = "tcms_review/get.html"


@method_decorator(permission_required("tcms_review.change_reviewrequest"), name="dispatch")
class Edit(UpdateView):
    model = ReviewRequest
    template_name = "tcms_review/mutable.html"
    fields = ["title", "description", "due_date", "reviewers"]


@method_decorator(permission_required("tcms_review.change_reviewrequest"), name="dispatch")
class Cancel(View):
    pass


@method_decorator(permission_required("tcms_review.change_reviewrequest"), name="dispatch")
class Vote(View):
    pass


@method_decorator(permission_required("tcms_review.change_reviewrequest"), name="dispatch")
class ItemDecision(View):
    pass


@method_decorator(permission_required("tcms_review.view_reviewrequest"), name="dispatch")
class Search(TemplateView):
    template_name = "tcms_review/search.html"


@method_decorator(permission_required("tcms_review.view_reviewrequest"), name="dispatch")
class Report(DetailView):
    model = ReviewRequest
    template_name = "tcms_review/report.html"
