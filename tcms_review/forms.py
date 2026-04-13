"""Form skeletons. Implemented incrementally per the build sequence in the plan."""
from django import forms

from tcms_review.models import ReviewRequest, ReviewVote


class NewReviewRequestForm(forms.ModelForm):
    class Meta:
        model = ReviewRequest
        fields = ["title", "description", "due_date", "reviewers"]

    def clean_reviewers(self):
        reviewers = self.cleaned_data.get("reviewers")
        if not reviewers:
            raise forms.ValidationError("At least one reviewer is required.")
        return reviewers


class VoteForm(forms.ModelForm):
    class Meta:
        model = ReviewVote
        fields = ["decision", "comment"]
