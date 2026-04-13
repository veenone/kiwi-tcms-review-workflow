from django import forms
from django.utils.translation import gettext_lazy as _

from tcms_review.models import ReviewRequest, ReviewVote
from tcms_review.state_machine import VoteDecision


def _simplemde_widget():
    """Lazy import — only load Kiwi widgets when a form actually instantiates."""
    from tcms.core.widgets import SimpleMDE  # noqa: WPS433
    return SimpleMDE()


class NewReviewRequestForm(forms.ModelForm):
    class Meta:
        model = ReviewRequest
        fields = ["title", "description", "due_date", "reviewers"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "required": True}),
            "due_date": forms.DateTimeInput(
                attrs={"class": "form-control date-picker", "autocomplete": "off"},
                format="%Y-%m-%d %H:%M",
            ),
            "reviewers": forms.SelectMultiple(
                attrs={
                    "class": "selectpicker",
                    "data-live-search": "true",
                    "data-actions-box": "true",
                    "data-selected-text-format": "count > 2",
                },
            ),
        }
        labels = {
            "title": _("Title"),
            "description": _("Description"),
            "due_date": _("Due date"),
            "reviewers": _("Reviewers"),
        }
        help_texts = {
            "title": _("A short summary describing what's being reviewed."),
            "due_date": _("Optional. Reviewers see overdue requests on their dashboard."),
            "reviewers": _("Pick one or more users. Each must approve before the request closes."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].widget = _simplemde_widget()
        self.fields["description"].required = False

    def clean_reviewers(self):
        reviewers = self.cleaned_data.get("reviewers")
        if not reviewers:
            raise forms.ValidationError(_("At least one reviewer is required."))
        return reviewers


class VoteForm(forms.ModelForm):
    class Meta:
        model = ReviewVote
        fields = ["decision", "comment"]
        widgets = {
            "decision": forms.RadioSelect(choices=VoteDecision.CHOICES),
        }
        labels = {
            "decision": _("Your decision"),
            "comment": _("Comment (optional)"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["comment"].widget = _simplemde_widget()
        self.fields["comment"].required = False
