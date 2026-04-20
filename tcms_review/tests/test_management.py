"""Tests for the tcms_review_grant_perms management command."""
from io import StringIO

from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase


class GrantPermsCommandTests(TestCase):
    def _clear_tester_perms(self):
        tester = Group.objects.get(name="Tester")
        review_perms = Permission.objects.filter(
            content_type__app_label="tcms_review",
        )
        tester.permissions.remove(*review_perms)

    def test_default_targets_tester_and_administrator(self):
        self._clear_tester_perms()
        out = StringIO()
        call_command("tcms_review_grant_perms", stdout=out)
        tester = Group.objects.get(name="Tester")
        self.assertTrue(
            tester.permissions.filter(
                content_type__app_label="tcms_review",
                codename="view_reviewrequest",
            ).exists(),
            msg="Tester should have view_reviewrequest after the command runs",
        )
        output = out.getvalue()
        self.assertIn("Tester", output)

    def test_custom_group_via_flag(self):
        Group.objects.create(name="Leader")
        out = StringIO()
        call_command("tcms_review_grant_perms", "--group", "Leader", stdout=out)
        leader = Group.objects.get(name="Leader")
        self.assertTrue(
            leader.permissions.filter(
                content_type__app_label="tcms_review",
            ).exists(),
        )

    def test_unknown_group_produces_warning_not_crash(self):
        out = StringIO()
        # Running against a nonexistent group should raise CommandError
        # (no groups matched), but shouldn't traceback.
        with self.assertRaises(CommandError):
            call_command(
                "tcms_review_grant_perms",
                "--group", "NoSuchGroupAnywhere",
                stdout=out,
            )
