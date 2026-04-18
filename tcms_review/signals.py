"""Signal handlers wired in apps.py::ready().

Sends notification emails using Kiwi's mailto helper. All Kiwi imports are
lazy so apps.py never pulls tcms.* at module load time.
"""
from django.db.models.signals import m2m_changed, post_save, pre_save
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from tcms_review.conf import get_status_transitions
from tcms_review.state_machine import State

_PRE_SAVE_STATE_ATTR = "_tcms_review_previous_state"


def _mailto(template_name, subject, recipients, context):
    """Lazy-import Kiwi's mail helper to keep startup decoupled."""
    from tcms.core.utils.mailto import mailto  # noqa: WPS433
    mailto(
        template_name=template_name,
        subject=subject,
        recipients=recipients,
        context=context,
    )


def _absolute_url(request):
    path = reverse("review-get", args=[request.pk])
    return path


def cache_previous_state(sender, instance, **kwargs):
    """Stash the prior state so post_save can detect transitions."""
    if instance.pk:
        previous = (
            sender.objects
            .filter(pk=instance.pk)
            .values_list("state", flat=True)
            .first()
        )
        setattr(instance, _PRE_SAVE_STATE_ATTR, previous)
    else:
        setattr(instance, _PRE_SAVE_STATE_ATTR, None)


def handle_emails_post_review_request_save(sender, instance, created, **kwargs):
    """Notify the requester when the state transitions.

    Reviewer invites are sent from the `m2m_changed` handler instead, because
    `CreateView.form_valid` runs `form.save_m2m()` AFTER the initial save, so
    the `reviewers` M2M is empty at post_save time when `created=True`.
    """
    if kwargs.get("raw"):
        return
    if created:
        return

    previous = getattr(instance, _PRE_SAVE_STATE_ATTR, None)
    if not previous or previous == instance.state:
        return
    if not instance.requester.email:
        return

    _mailto(
        template_name="email/review_request/state_changed.txt",
        subject=str(_("Review request #%(pk)d is now %(state)s")) % {
            "pk": instance.pk, "state": instance.get_state_display(),
        },
        recipients=[instance.requester.email],
        context={
            "review_request": instance,
            "previous_state": previous,
            "absolute_url": _absolute_url(instance),
        },
    )


def handle_reviewers_changed(sender, instance, action, pk_set, **kwargs):
    """Email newly-assigned reviewers when they're added to the M2M.

    Fired by Django's `m2m_changed` signal. We only care about `post_add`.
    """
    if action != "post_add":
        return
    if not pk_set:
        return

    from django.contrib.auth import get_user_model  # noqa: WPS433
    User = get_user_model()

    recipients = [
        email for email in User.objects
        .filter(pk__in=pk_set)
        .values_list("email", flat=True)
        if email
    ]
    if not recipients:
        return

    _mailto(
        template_name="email/review_request/assigned.txt",
        subject=str(_("Review request #%(pk)d: %(title)s")) % {
            "pk": instance.pk, "title": instance.title,
        },
        recipients=recipients,
        context={
            "review_request": instance,
            "absolute_url": _absolute_url(instance),
        },
    )


def handle_emails_post_review_vote_save(sender, instance, created, **kwargs):
    if kwargs.get("raw"):
        return

    requester = instance.review_request.requester
    if requester.email:
        _mailto(
            template_name="email/review_request/vote_cast.txt",
            subject=str(_("Vote on review request #%(pk)d: %(decision)s")) % {
                "pk": instance.review_request.pk,
                "decision": instance.get_decision_display(),
            },
            recipients=[requester.email],
            context={
                "vote": instance,
                "absolute_url": _absolute_url(instance.review_request),
            },
        )

    # State machine runs on every vote save — the only place it runs
    # automatically. Cancelled requests short-circuit inside recalculate_state.
    if instance.review_request.state != State.CANCELLED:
        instance.review_request.recalculate_state()


def handle_testcase_status_transition(sender, instance, created, **kwargs):
    """Apply REVIEW_STATUS_TRANSITIONS when a ReviewItem decision changes.

    The setting maps (source_case_status, decision) -> target_case_status.
    When a ReviewItem.decision is updated and the linked TestCase's
    current status name matches the source, the case's status is set
    to the target. No-op for unmatched decisions.

    Skipped entirely when the plugin hasn't been configured with
    transitions, so default installs don't touch case statuses.
    """
    if kwargs.get("raw"):
        return

    transitions = get_status_transitions()
    if not transitions:
        return

    from tcms.testcases.models import TestCaseStatus  # noqa: WPS433

    case = instance.case
    if case is None or case.case_status is None:
        return

    key = (case.case_status.name.upper(), instance.decision.lower())
    target = transitions.get(key)
    if not target:
        return

    try:
        target_status = TestCaseStatus.objects.get(name__iexact=target)
    except TestCaseStatus.DoesNotExist:
        return

    if case.case_status_id == target_status.pk:
        return

    case.case_status = target_status
    case.save(update_fields=["case_status"])
