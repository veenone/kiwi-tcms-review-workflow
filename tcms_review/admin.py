from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from tcms_review.models import ReviewItem, ReviewRequest, ReviewVote


@admin.register(ReviewRequest)
class ReviewRequestAdmin(SimpleHistoryAdmin):
    list_display = ("pk", "title", "state", "requester", "due_date", "created_at")
    list_filter = ("state",)
    search_fields = ("title", "description")


@admin.register(ReviewItem)
class ReviewItemAdmin(SimpleHistoryAdmin):
    list_display = ("pk", "review_request", "case", "decision", "updated_at")
    list_filter = ("decision",)


@admin.register(ReviewVote)
class ReviewVoteAdmin(SimpleHistoryAdmin):
    list_display = ("pk", "review_request", "reviewer", "decision", "voted_at")
    list_filter = ("decision",)
