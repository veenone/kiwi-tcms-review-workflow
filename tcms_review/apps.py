from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import m2m_changed, post_migrate, post_save, pre_save


def _grant_tester_permissions_post_migrate(sender, **kwargs):
    """Fallback grant: run after core apps have created Permission rows.

    Migration 0002_add_permissions tries to force-create our permissions
    inline, but on installs with a broken django_content_type schema
    (legacy NOT NULL `name` column) that step no-ops. This handler
    retries the grant after post_migrate, at which point the core
    Django auth/contenttypes machinery has had a chance to populate
    Permission rows (if it could).
    """
    from tcms_review.permissions import grant_permissions_to_groups  # noqa: WPS433

    grant_permissions_to_groups()


class ReviewConfig(AppConfig):
    name = "tcms_review"
    verbose_name = "Test Case Review"

    def ready(self):
        # Register system checks — importing the module executes the
        # @register decorators, which plug our checks into Django's
        # `./manage.py check` and the runserver/boot-time probe.
        from tcms_review import checks  # noqa: F401,WPS433

        # Register RPC methods directly into the modernrpc registry.
        # We can't just append to MODERNRPC_METHODS_MODULES because
        # modernrpc.apps.ModernRpcConfig.ready() scans that list BEFORE
        # plugin apps run ready() — by the time we append, the scan is done.
        self._register_rpc_methods()

        # Register the response-rewriting middleware that injects the
        # plugin's JS bundle into every HTML response so the "Send for
        # review" button / per-case badge / dashboard widget all work on
        # Kiwi core pages without editing any core template. ready() runs
        # before Django's BaseHandler lazy-loads the middleware chain, so
        # appending here is safe.
        middleware_path = "tcms_review.middleware.InjectReviewBundleMiddleware"
        if middleware_path not in settings.MIDDLEWARE:
            settings.MIDDLEWARE = list(settings.MIDDLEWARE) + [middleware_path]

        from tcms_review import signals as review_signals  # noqa: WPS433
        from tcms_review.models import ReviewItem, ReviewRequest, ReviewVote

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
        post_save.connect(
            review_signals.handle_wiki_sync_post_review_request_save,
            sender=ReviewRequest,
            dispatch_uid="tcms_review.wiki_sync_post_request_save",
        )
        post_save.connect(
            review_signals.handle_wiki_sync_post_review_item_save,
            sender=ReviewItem,
            dispatch_uid="tcms_review.wiki_sync_post_item_save",
        )
        pre_save.connect(
            review_signals.cache_previous_vote_decision,
            sender=ReviewVote,
            dispatch_uid="tcms_review.cache_previous_vote_decision",
        )
        post_save.connect(
            review_signals.handle_wiki_sync_post_review_vote_save,
            sender=ReviewVote,
            dispatch_uid="tcms_review.wiki_sync_post_vote_save",
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
        post_save.connect(
            review_signals.handle_testcase_status_transition,
            sender=ReviewItem,
            dispatch_uid="tcms_review.status_transition",
        )
        pre_save.connect(
            review_signals.cache_previous_item_decision,
            sender=ReviewItem,
            dispatch_uid="tcms_review.cache_previous_item_decision",
        )
        post_save.connect(
            review_signals.handle_email_item_resubmitted,
            sender=ReviewItem,
            dispatch_uid="tcms_review.email_item_resubmitted",
        )
        post_migrate.connect(
            _grant_tester_permissions_post_migrate,
            sender=self,
            dispatch_uid="tcms_review.grant_tester_permissions_post_migrate",
        )

    @staticmethod
    def _register_rpc_methods():
        """Register tcms_review.api methods directly into the modernrpc
        registry. This mirrors what modernrpc.apps.import_modules() does
        but runs from the plugin's own ready() — after modernrpc has
        already finished its scan of MODERNRPC_METHODS_MODULES."""
        import inspect  # noqa: WPS433

        from modernrpc.core import registry  # noqa: WPS433

        import tcms_review.api as api_module  # noqa: WPS433

        for _, func in inspect.getmembers(api_module, inspect.isfunction):
            if getattr(func, "modernrpc_enabled", False):
                registry.register_method(func)
