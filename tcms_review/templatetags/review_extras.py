from django import template
from django.templatetags.static import static
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from tcms_review import __version__
from tcms_review.state_machine import State, VoteDecision

register = template.Library()


@register.simple_tag
def format_duration(td):
    """Render a timedelta as 'HHh MMm SSs MMMms' with unit labels.

    Kiwi users asked for explicit units so the time-to-decision KPIs read
    unambiguously. Returns an em-dash for None / missing values.
    """
    if td is None:
        return "—"
    total_ms = int(td.total_seconds() * 1000)
    if total_ms < 0:
        total_ms = 0
    hours, rem_ms = divmod(total_ms, 3_600_000)
    minutes, rem_ms = divmod(rem_ms, 60_000)
    seconds, ms = divmod(rem_ms, 1000)
    return f"{hours:02d}h {minutes:02d}m {seconds:02d}s {ms:03d}ms"


@register.simple_tag
def review_static(path):
    """Like {% static %} but with the plugin version appended as a cache-buster.

    Usage:
        {% load review_extras %}
        <link rel="stylesheet" href="{% review_static 'tcms_review/css/review.css' %}">

    Browsers will re-fetch the asset on every plugin version bump without
    the operator needing to configure ManifestStaticFilesStorage.
    """
    return f"{static(path)}?v={__version__}"


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


def _label(text, css_class, icon=None, role=None, pill=False):
    icon_html = f'<i class="{icon}" aria-hidden="true"></i> ' if icon else ""
    role_attr = f' role="{role}"' if role else ""
    pill_class = " review-label-pill" if pill else ""
    return mark_safe(  # nosec: rendered values are class names + already-translated labels
        f'<span class="label {css_class}{pill_class}"{role_attr}>{icon_html}{text}</span>'
    )


_DECISION_ICON = {
    VoteDecision.APPROVED: "pficon pficon-ok",
    VoteDecision.REJECTED: "pficon pficon-error-circle-o",
    VoteDecision.NEEDS_CHANGES: "pficon pficon-warning-triangle-o",
    "pending": "fa fa-hourglass-half",
}


@register.simple_tag
def state_badge(state, display=None):
    css = _STATE_LABEL_CLASS.get(state, "label-default")
    icon = _STATE_ICON.get(state)
    label = display or dict(State.CHOICES).get(state, state)
    return _label(label, css, icon=icon, role="status", pill=True)


@register.simple_tag
def decision_badge(decision, display=None):
    css = _DECISION_LABEL_CLASS.get(decision, "label-default")
    icon = _DECISION_ICON.get(decision)
    label = display or decision.replace("_", " ").title()
    return _label(label, css, icon=icon, role="status", pill=True)


@register.filter
def vote_for(votes, reviewer):
    """Return the vote cast by a given reviewer, or None."""
    for vote in votes:
        if vote.reviewer_id == reviewer.pk:
            return vote
    return None
