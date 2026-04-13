"""Signal handlers wired in apps.py::ready().

Sends notification emails using Kiwi's mailto helper. Skeleton — flesh out
per the build sequence in the plan.
"""
from django.utils.translation import gettext_lazy as _
from tcms.core.utils.mailto import mailto

from tcms_review.state_machine import State

_PRE_SAVE_STATE_ATTR = "_tcms_review_previous_state"


def cache_previous_state(sender, instance, **kwargs):
    """Stash the prior state on the instance so post_save can detect transitions."""
    if instance.pk:
        previous = sender.objects.filter(pk=instance.pk).values_list("state", flat=True).first()
        setattr(instance, _PRE_SAVE_STATE_ATTR, previous)
    else:
        setattr(instance, _PRE_SAVE_STATE_ATTR, None)


def handle_emails_post_review_request_save(sender, instance, created, **kwargs):
    if kwargs.get("raw"):
        return

    if created:
        recipients = [u.email for u in instance.reviewers.all() if u.email]
        if recipients:
            mailto(
                template_name="email/review_request/assigned.txt",
                subject=str(_("Review request #%(pk)d: %(title)s")) % {
                    "pk": instance.pk, "title": instance.title,
                },
                recipients=recipients,
                context={"review_request": instance},
            )
        return

    previous = getattr(instance, _PRE_SAVE_STATE_ATTR, None)
    if previous and previous != instance.state and instance.requester.email:
        mailto(
            template_name="email/review_request/state_changed.txt",
            subject=str(_("Review request #%(pk)d is now %(state)s")) % {
                "pk": instance.pk, "state": instance.get_state_display(),
            },
            recipients=[instance.requester.email],
            context={"review_request": instance, "previous_state": previous},
        )


def handle_emails_post_review_vote_save(sender, instance, created, **kwargs):
    if kwargs.get("raw"):
        return
    requester = instance.review_request.requester
    if not requester.email:
        return
    mailto(
        template_name="email/review_request/vote_cast.txt",
        subject=str(_("Vote on review request #%(pk)d: %(decision)s")) % {
            "pk": instance.review_request.pk,
            "decision": instance.get_decision_display(),
        },
        recipients=[requester.email],
        context={"vote": instance},
    )
    instance.review_request.recalculate_state()
