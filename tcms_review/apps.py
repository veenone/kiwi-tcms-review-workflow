from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import m2m_changed, post_save, pre_save


class ReviewConfig(AppConfig):
    name = "tcms_review"
    verbose_name = "Test Case Review"

    def ready(self):
        # Register our XML-RPC module with modernrpc. Kiwi auto-discovers
        # plugin URLs and INSTALLED_APPS but does not extend
        # MODERNRPC_METHODS_MODULES, so we do it here.
        rpc_module = "tcms_review.api"
        if rpc_module not in settings.MODERNRPC_METHODS_MODULES:
            settings.MODERNRPC_METHODS_MODULES.append(rpc_module)

        from tcms_review import signals as review_signals
        from tcms_review.models import ReviewRequest, ReviewVote

        pre_save.connect(
            review_signals.cache_previous_state,
            sender=ReviewRequest,
            dispatch_uid="tcms_review.cache_previous_state",
        )
        post_save.connect(
            review_signals.handle_emails_post_review_request_save,
            sender=ReviewRequest,
            dispatch_uid="tcms_review.email_post_request_save",
        )
        m2m_changed.connect(
            review_signals.handle_reviewers_changed,
            sender=ReviewRequest.reviewers.through,
            dispatch_uid="tcms_review.email_reviewers_added",
        )
        post_save.connect(
            review_signals.handle_emails_post_review_vote_save,
            sender=ReviewVote,
            dispatch_uid="tcms_review.email_post_vote_save",
        )
