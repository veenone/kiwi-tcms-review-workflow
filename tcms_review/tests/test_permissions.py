from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from tcms.tests.factories import UserFactory

from tcms_review.tests.factory import ReviewRequestFactory


class TesterGroupPermissions(TestCase):
    def test_tester_group_has_review_permissions_after_migration(self):
        tester = Group.objects.get(name="Tester")
        codenames = set(
            tester.permissions.filter(
                content_type__app_label="tcms_review"
            ).values_list("codename", flat=True)
        )
        self.assertIn("add_reviewrequest", codenames)
        self.assertIn("change_reviewrequest", codenames)
        self.assertIn("view_reviewrequest", codenames)


class ViewPermissionEnforcement(TestCase):
    def test_anonymous_user_redirected_from_list(self):
        response = self.client.get(reverse("review-list"))
        self.assertEqual(response.status_code, 302)

    def test_user_without_view_permission_gets_forbidden(self):
        """Authenticated user lacking the perm gets a 403, NOT a redirect.

        Regression guard: without raise_exception=True on the view's
        permission_required decorator, Django would 302 the user to
        LOGIN_URL — producing an infinite login loop for already-logged-
        in users because they just authenticated.
        """
        user = UserFactory()
        # No permissions assigned — default user has no review.* perms
        self.client.force_login(user)
        response = self.client.get(reverse("review-list"))
        self.assertEqual(response.status_code, 403)

    def test_user_without_view_permission_does_not_redirect_to_login(self):
        """Paired check on the three views most visible from the menu."""
        user = UserFactory()
        self.client.force_login(user)
        for urlname in ("review-list", "review-stats", "review-report-hub"):
            response = self.client.get(reverse(urlname))
            self.assertEqual(
                response.status_code, 403,
                msg=f"{urlname} redirected instead of returning 403",
            )

    def test_user_with_view_permission_can_list(self):
        user = UserFactory()
        user.user_permissions.add(
            Permission.objects.get(codename="view_reviewrequest")
        )
        self.client.force_login(user)
        response = self.client.get(reverse("review-list"))
        self.assertEqual(response.status_code, 200)

    def test_non_requester_cannot_cancel(self):
        user = UserFactory()
        user.user_permissions.add(
            Permission.objects.get(codename="change_reviewrequest")
        )
        self.client.force_login(user)

        request = ReviewRequestFactory()  # requester is a different user
        response = self.client.post(reverse("review-cancel", args=[request.pk]))
        self.assertEqual(response.status_code, 403)

    def test_non_reviewer_cannot_vote(self):
        user = UserFactory()
        user.user_permissions.add(
            Permission.objects.get(codename="change_reviewrequest")
        )
        self.client.force_login(user)

        request = ReviewRequestFactory()  # user is not in reviewers M2M
        response = self.client.post(
            reverse("review-vote", args=[request.pk]),
            {"decision": "approved"},
        )
        self.assertEqual(response.status_code, 403)
