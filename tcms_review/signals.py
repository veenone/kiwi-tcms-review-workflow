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


_PRE_SAVE_ITEM_DECISION_ATTR = "_tcms_review_previous_item_decision"


def cache_previous_item_decision(sender, instance, **kwargs):
    """Stash the prior ReviewItem.decision so post_save can detect the
    transition from {needs_changes, rejected} -> pending (resubmit)."""
    if instance.pk:
        previous = (
            sender.objects
            .filter(pk=instance.pk)
            .values_list("decision", flat=True)
            .first()
        )
        setattr(instance, _PRE_SAVE_ITEM_DECISION_ATTR, previous)
    else:
        setattr(instance, _PRE_SAVE_ITEM_DECISION_ATTR, None)


def handle_email_item_resubmitted(sender, instance, created, **kwargs):
    """When a ReviewItem.decision transitions from needs_changes or
    rejected back to pending, email every assigned reviewer so they
    know the tester has updated the case and wants another look."""
    if kwargs.get("raw"):
        return
    if created:
        return

    previous = getattr(instance, _PRE_SAVE_ITEM_DECISION_ATTR, None)
    if previous not in ("needs_changes", "rejected"):
        return
    if instance.decision != "pending":
        return

    review_request = instance.review_request
    recipients = [
        email for email in review_request.reviewers.values_list("email", flat=True)
        if email
    ]
    if not recipients:
        return

    _mailto(
        template_name="email/review_request/resubmitted.txt",
        subject=str(_("Re-review requested: Case #%(case_id)d in Review Request #%(pk)d")) % {
            "case_id": instance.case_id,
            "pk": review_request.pk,
        },
        recipients=recipients,
        context={
            "review_request": review_request,
            "item": instance,
            "previous_decision": previous,
            "absolute_url": _absolute_url(review_request),
        },
    )


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


# ─── Wiki sync ────────────────────────────────────────────────────────


def _fire_wiki_sync(fn, *args, **kwargs):
    """Run a wiki call in a daemon thread so the HTTP round-trip never
    blocks the request cycle. Mirrors the pattern Kiwi uses for mailto."""
    import threading  # noqa: WPS433

    def _runner():
        try:
            fn(*args, **kwargs)
        except Exception:  # noqa: BLE001 — log everything, never bubble
            import logging  # noqa: WPS433
            logging.getLogger("tcms_review.wiki").exception(
                "Wiki sync failed for %s", fn.__name__,
            )

    threading.Thread(target=_runner, daemon=True).start()


def _do_wiki_create(review_request):
    from tcms_review.integrations.wiki.adapters import get_adapter, WikiSyncError  # noqa: WPS433
    from tcms_review.integrations.wiki import builder  # noqa: WPS433
    from tcms_review.models import WikiIntegrationConfig  # noqa: WPS433

    config = WikiIntegrationConfig.objects.first()
    if not config or not config.auto_create:
        return
    adapter = get_adapter(config)
    if adapter is None:
        return

    try:
        page_id = adapter.create_page(
            title=builder.build_title(review_request),
            body_md=builder.build_create_body(review_request),
        )
    except WikiSyncError:
        raise
    # Persist the id without re-triggering post_save signals.
    from tcms_review.models import ReviewRequest  # noqa: WPS433
    ReviewRequest.objects.filter(pk=review_request.pk).update(wiki_page_id=page_id)


def _do_wiki_update(review_request, previous_state, event="state_changed"):
    from tcms_review.integrations.wiki.adapters import get_adapter, WikiSyncError  # noqa: WPS433
    from tcms_review.integrations.wiki import builder  # noqa: WPS433
    from tcms_review.models import WikiIntegrationConfig, ReviewRequest  # noqa: WPS433

    if not review_request.wiki_page_id:
        return
    config = WikiIntegrationConfig.objects.first()
    if not config or not config.auto_update:
        return
    adapter = get_adapter(config)
    if adapter is None:
        return

    # Re-fetch from DB to make sure the rebuild sees the current state
    # (callers sometimes pass an instance captured before a save).
    review_request = ReviewRequest.objects.get(pk=review_request.pk)

    body = builder.build_full_body(review_request)
    try:
        adapter.update_page(review_request.wiki_page_id, body, append=False)
    except WikiSyncError:
        raise


def handle_wiki_sync_post_review_request_save(
    sender, instance, created, **kwargs,
):
    """Fire-and-forget wiki sync on ReviewRequest save — state changes only.

    The initial page create is triggered by the first ReviewItem save via
    handle_wiki_sync_post_review_item_save, because `ReviewRequest.save()`
    fires before `form.save_m2m()` has populated the reviewers M2M and
    before any ReviewItem rows exist. Creating the page later lets the
    initial body include both reviewers and attached cases.
    """
    if kwargs.get("raw"):
        return

    if created:
        return

    previous_state = getattr(instance, _PRE_SAVE_STATE_ATTR, None)
    if previous_state and previous_state != instance.state:
        _fire_wiki_sync(_do_wiki_update, instance, previous_state)


# ─── Wiki sync — per-item and per-vote events ─────────────────────────


_PRE_SAVE_VOTE_DECISION_ATTR = "_tcms_review_previous_vote_decision"


def cache_previous_vote_decision(sender, instance, **kwargs):
    """Stash the prior ReviewVote.decision so post_save can diff."""
    if instance.pk:
        previous = (
            sender.objects
            .filter(pk=instance.pk)
            .values_list("decision", flat=True)
            .first()
        )
        setattr(instance, _PRE_SAVE_VOTE_DECISION_ATTR, previous)
    else:
        setattr(instance, _PRE_SAVE_VOTE_DECISION_ATTR, None)


def _do_wiki_append_item_decision(review_request, item, previous_decision, actor):
    from tcms_review.integrations.wiki.adapters import get_adapter, WikiSyncError  # noqa: WPS433
    from tcms_review.integrations.wiki import builder  # noqa: WPS433
    from tcms_review.models import WikiIntegrationConfig, ReviewRequest  # noqa: WPS433

    config = WikiIntegrationConfig.objects.first()
    if not config:
        return
    adapter = get_adapter(config)
    if adapter is None:
        return

    # Re-fetch to get the freshest state — reviewers M2M, items, votes —
    # before rebuilding the body.
    review_request = ReviewRequest.objects.get(pk=review_request.pk)

    # Lazy create: if the request has no wiki page yet AND auto_create
    # is on, create it now. By the first ReviewItem save the reviewers
    # M2M is populated, so the initial body reflects the real state.
    if not review_request.wiki_page_id:
        if not config.auto_create:
            return
        title = builder.build_title(review_request)
        body_md = builder.build_full_body(review_request)
        page_id = adapter.create_page(title=title, body_md=body_md)
        ReviewRequest.objects.filter(pk=review_request.pk).update(
            wiki_page_id=page_id,
        )
        return

    if not config.auto_update:
        return

    body = builder.build_full_body(review_request)
    adapter.update_page(review_request.wiki_page_id, body, append=False)


def _do_wiki_append_vote_cast(review_request, vote, previous_decision, actor):
    from tcms_review.integrations.wiki.adapters import get_adapter, WikiSyncError  # noqa: WPS433
    from tcms_review.integrations.wiki import builder  # noqa: WPS433
    from tcms_review.models import WikiIntegrationConfig, ReviewRequest  # noqa: WPS433

    if not review_request.wiki_page_id:
        return
    config = WikiIntegrationConfig.objects.first()
    if not config or not config.auto_update:
        return
    adapter = get_adapter(config)
    if adapter is None:
        return

    review_request = ReviewRequest.objects.get(pk=review_request.pk)
    body = builder.build_full_body(review_request)
    adapter.update_page(review_request.wiki_page_id, body, append=False)


def handle_wiki_sync_post_review_item_save(sender, instance, created, **kwargs):
    """Append a per-case decision entry to the wiki page whenever a
    ReviewItem is created or its decision changes."""
    if kwargs.get("raw"):
        return

    previous = getattr(instance, _PRE_SAVE_ITEM_DECISION_ATTR, None)
    # Skip no-op saves (e.g. bumping updated_at without changing decision)
    if not created and previous == instance.decision and not instance.comment:
        return

    actor = (
        instance.case.author.username
        if instance.case_id and instance.case and instance.case.author_id
        else "system"
    )
    _fire_wiki_sync(
        _do_wiki_append_item_decision,
        instance.review_request, instance, previous, actor,
    )


def handle_wiki_sync_post_review_vote_save(sender, instance, created, **kwargs):
    """Append a per-reviewer vote entry to the wiki page whenever a vote
    is cast or revised."""
    if kwargs.get("raw"):
        return

    previous = getattr(instance, _PRE_SAVE_VOTE_DECISION_ATTR, None)
    if not created and previous == instance.decision and not instance.comment:
        return

    actor = instance.reviewer.username if instance.reviewer_id else "system"
    _fire_wiki_sync(
        _do_wiki_append_vote_cast,
        instance.review_request, instance, previous, actor,
    )
