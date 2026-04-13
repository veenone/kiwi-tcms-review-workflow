from django import template
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from tcms_review.state_machine import State, VoteDecision

register = template.Library()


_STATE_LABEL_CLASS = {
    State.IN_REVIEW: "label-info",
    State.APPROVED: "label-success",
    State.REJECTED: "label-danger",
    State.CHANGES_REQUESTED: "label-warning",
    State.CANCELLED: "label-default",
}

_STATE_ICON = {
    State.IN_REVIEW: "fa fa-hourglass-half",
    State.APPROVED: "pficon pficon-ok",
    State.REJECTED: "pficon pficon-error-circle-o",
    State.CHANGES_REQUESTED: "pficon pficon-warning-triangle-o",
    State.CANCELLED: "pficon pficon-close",
}

_DECISION_LABEL_CLASS = {
    VoteDecision.APPROVED: "label-success",
    VoteDecision.REJECTED: "label-danger",
    VoteDecision.NEEDS_CHANGES: "label-warning",
    "pending": "label-default",
}


def _label(text, css_class, icon=None, role=None):
    icon_html = f'<i class="{icon}" aria-hidden="true"></i> ' if icon else ""
    role_attr = f' role="{role}"' if role else ""
    return mark_safe(  # nosec: rendered values are class names + already-translated labels
        f'<span class="label {css_class}"{role_attr}>{icon_html}{text}</span>'
    )


@register.simple_tag
def state_badge(state, display=None):
    css = _STATE_LABEL_CLASS.get(state, "label-default")
    icon = _STATE_ICON.get(state)
    label = display or dict(State.CHOICES).get(state, state)
    return _label(label, css, icon=icon, role="status")


@register.simple_tag
def decision_badge(decision, display=None):
    css = _DECISION_LABEL_CLASS.get(decision, "label-default")
    label = display or decision.replace("_", " ").title()
    return _label(label, css)


@register.filter
def vote_for(votes, reviewer):
    """Return the vote cast by a given reviewer, or None."""
    for vote in votes:
        if vote.reviewer_id == reviewer.pk:
            return vote
    return None
