"""Regression guards for the plugin's migration chain.

The test runner applies every migration before running any test, so if
the chain crashes the entire suite refuses to start. These tests just
pin down the specific invariants we care about so a regression in one
of them produces a clear failure rather than a cryptic `migrate` error.
"""
from django.apps import apps
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase


class MigrationChainTests(TestCase):
    """The 8 tcms_review migrations must all be marked applied, and the
    expected tables and default transition rows must exist."""

    def test_all_migrations_applied(self):
        loader = MigrationLoader(connection)
        applied_for_app = {
            migration
            for app_label, migration in loader.applied_migrations
            if app_label == "tcms_review"
        }
        self.assertGreaterEqual(
            len(applied_for_app), 8,
            msg=f"Expected at least 8 migrations applied, got {sorted(applied_for_app)}",
        )

    def test_review_tables_exist(self):
        tables = set(connection.introspection.table_names())
        for expected in (
            "tcms_review_reviewrequest",
            "tcms_review_reviewitem",
            "tcms_review_reviewvote",
            "tcms_review_reviewconfig",
            "tcms_review_reviewstatustransition",
            "tcms_review_wikiintegrationconfig",
        ):
            self.assertIn(expected, tables)

    def test_default_transitions_seeded(self):
        """0005 + 0006 seed the PROPOSED/CONFIRMED/NEED_UPDATE/DISABLED
        rules. A regression in the get_or_create path (e.g. swallowing
        the seed entirely) would leave the table empty."""
        Transition = apps.get_model("tcms_review", "ReviewStatusTransition")
        rules = {
            (row.source_status, row.decision): row.target_status
            for row in Transition.objects.all()
        }
        self.assertEqual(rules.get(("PROPOSED", "approved")), "CONFIRMED")
        self.assertEqual(rules.get(("PROPOSED", "needs_changes")), "NEED_UPDATE")
        self.assertEqual(rules.get(("PROPOSED", "rejected")), "DISABLED")
        self.assertEqual(rules.get(("NEED_UPDATE", "pending")), "PROPOSED")
        self.assertEqual(rules.get(("DISABLED", "pending")), "PROPOSED")


class DataMigrationAtomicityTests(TestCase):
    """The three data migrations (0002, 0005, 0006) must declare
    atomic = False. Protects against a regression that would re-
    introduce the SQLite TransactionManagementError on install.
    """

    def test_data_migrations_are_non_atomic(self):
        from importlib import import_module

        for name in (
            "tcms_review.migrations.0002_add_permissions",
            "tcms_review.migrations.0005_seed_default_transitions",
            "tcms_review.migrations.0006_resubmit_transitions",
        ):
            module = import_module(name)
            self.assertFalse(
                getattr(module.Migration, "atomic", True),
                msg=f"{name}: atomic must be False to avoid SQLite "
                f"savepoint contamination during create_permissions / "
                f"get_or_create.",
            )
