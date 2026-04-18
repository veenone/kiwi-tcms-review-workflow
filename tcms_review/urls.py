from django.urls import re_path

from tcms_review import views

urlpatterns = [
    re_path(r"^$", views.List.as_view(), name="review-list"),
    re_path(r"^new/$", views.New.as_view(), name="review-new"),
    re_path(r"^(?P<pk>\d+)/$", views.Get.as_view(), name="review-get"),
    re_path(r"^(?P<pk>\d+)/edit/$", views.Edit.as_view(), name="review-edit"),
    re_path(r"^(?P<pk>\d+)/cancel/$", views.Cancel.as_view(), name="review-cancel"),
    re_path(r"^(?P<pk>\d+)/vote/$", views.Vote.as_view(), name="review-vote"),
    re_path(r"^(?P<pk>\d+)/report/$", views.Report.as_view(), name="review-report"),
    re_path(r"^item/(?P<pk>\d+)/decision/$", views.ItemDecision.as_view(), name="review-item-decision"),
    re_path(r"^item/(?P<pk>\d+)/resubmit/$", views.ResubmitItem.as_view(), name="review-item-resubmit"),
    re_path(r"^search/$", views.Search.as_view(), name="review-search"),
    re_path(r"^stats/$", views.Stats.as_view(), name="review-stats"),
    # JSON endpoints consumed by inject.js (dashboard widget, per-case badge, config)
    re_path(r"^json/pending-mine/$", views.PendingMineJSON.as_view(), name="review-json-pending-mine"),
    re_path(r"^json/case/(?P<case_pk>\d+)/latest/$", views.CaseLatestJSON.as_view(), name="review-json-case-latest"),
    re_path(r"^json/allowed-statuses/$", views.AllowedStatusesJSON.as_view(), name="review-json-allowed-statuses"),
]
