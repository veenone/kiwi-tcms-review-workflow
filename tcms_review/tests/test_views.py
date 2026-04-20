from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.db.utils import DatabaseError
from django.test import TestCase
from django.urls import reverse

from tcms.tests.factories import TestCaseFactory, UserFactory

from tcms_review.models import ReviewItem, ReviewRequest, ReviewVote
from tcms_review.state_machine import State, VoteDecision
from tcms_review.tests.factory import ReviewItemFactory, ReviewRequestFactory


def _grant_all(user):
    for codename in (
        "add_reviewrequest",
        "change_reviewrequest",
        "view_reviewrequest",
    ):
        user.user_permissions.add(Permission.objects.get(codename=codename))


class ListViewTests(TestCase):
    def setUp(self):
        self.user = UserFactory()
        _grant_all(self.user)
        self.client.force_login(self.user)

    def test_list_renders_for_user_with_view_permission(self):
        response = self.client.get(reverse("review-list"))
        self.assertEqual(response.status_code, 200)

    def test_list_filters_by_state(self):
        ReviewRequestFactory(state=State.IN_REVIEW)
        ReviewRequestFactory(state=State.APPROVED)
        response = self.client.get(reverse("review-list") + "?state=approved")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["review_requests"]), 1)

    def test_list_filters_by_mine_only(self):
        ReviewRequestFactory(reviewers=[self.user])
        ReviewRequestFactory()
        response = self.client.get(reverse("review-list") + "?mine_only=1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["review_requests"]), 1)


class NewViewTests(TestCase):
    def setUp(self):
        self.user = UserFactory()
        _grant_all(self.user)
        self.client.force_login(self.user)

    def test_new_creates_review_request_with_current_user_as_requester(self):
        reviewer = UserFactory()
        response = self.client.post(
            reverse("review-new"),
            {
                "title": "Audit payments",
                "description": "Please review",
                "due_date": "",
                "reviewers": [reviewer.pk],
            },
        )
        self.assertEqual(response.status_code, 302)
        request = ReviewRequest.objects.get(title="Audit payments")
        self.assertEqual(request.requester, self.user)
        self.assertIn(reviewer, request.reviewers.all())

    def test_new_attaches_testcase_from_query_param(self):
        reviewer = UserFactory()
        case = TestCaseFactory()
        response = self.client.post(
            reverse("review-new") + f"?testcase={case.pk}",
            {
                "title": "Review one case",
                "description": "",
                "due_date": "",
                "reviewers": [reviewer.pk],
            },
        )
        self.assertEqual(response.status_code, 302)
        request = ReviewRequest.objects.get(title="Review one case")
        self.assertIn(case, request.cases.all())


class VoteViewTests(TestCase):
    def setUp(self):
        self.reviewer = UserFactory()
        _grant_all(self.reviewer)
        self.request_obj = ReviewRequestFactory(reviewers=[self.reviewer])
        self.client.force_login(self.reviewer)

    def test_reviewer_can_cast_vote(self):
        response = self.client.post(
            reverse("review-vote", args=[self.request_obj.pk]),
            {"decision": VoteDecision.APPROVED, "comment": "looks good"},
        )
        self.assertEqual(response.status_code, 302)
        vote = ReviewVote.objects.get(
            review_request=self.request_obj,
            reviewer=self.reviewer,
        )
        self.assertEqual(vote.decision, VoteDecision.APPROVED)

    def test_revote_updates_existing_vote(self):
        self.client.post(
            reverse("review-vote", args=[self.request_obj.pk]),
            {"decision": VoteDecision.APPROVED},
        )
        self.client.post(
            reverse("review-vote", args=[self.request_obj.pk]),
            {"decision": VoteDecision.REJECTED, "comment": "changed mind"},
        )
        votes = ReviewVote.objects.filter(
            review_request=self.request_obj,
            reviewer=self.reviewer,
        )
        self.assertEqual(votes.count(), 1)
        self.assertEqual(votes.first().decision, VoteDecision.REJECTED)


class CancelViewTests(TestCase):
    def test_requester_can_cancel(self):
        user = UserFactory()
        _grant_all(user)
        request = ReviewRequestFactory(requester=user)
        self.client.force_login(user)

        response = self.client.post(reverse("review-cancel", args=[request.pk]))
        self.assertEqual(response.status_code, 302)
        request.refresh_from_db()
        self.assertEqual(request.state, State.CANCELLED)


class ItemDecisionViewTests(TestCase):
    def test_item_decision_updates_to_whitelisted_value(self):
        user = UserFactory()
        _grant_all(user)
        self.client.force_login(user)

        item = ReviewItemFactory()
        response = self.client.post(
            reverse("review-item-decision", args=[item.pk]),
            {"decision": VoteDecision.APPROVED, "comment": "passes"},
        )
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.decision, VoteDecision.APPROVED)

    def test_item_decision_rejects_invalid_value(self):
        user = UserFactory()
        _grant_all(user)
        self.client.force_login(user)

        item = ReviewItemFactory()
        response = self.client.post(
            reverse("review-item-decision", args=[item.pk]),
            {"decision": "not-a-real-decision"},
        )
        self.assertEqual(response.status_code, 403)


class JsonEndpointTests(TestCase):
    def test_pending_mine_returns_only_unvoted_in_review_requests(self):
        user = UserFactory()
        _grant_all(user)
        self.client.force_login(user)

        # Open request assigned to me, not yet voted on
        mine = ReviewRequestFactory(reviewers=[user], state=State.IN_REVIEW)
        # Open request assigned to someone else
        ReviewRequestFactory(state=State.IN_REVIEW)
        # Approved request assigned to me
        ReviewRequestFactory(reviewers=[user], state=State.APPROVED)

        response = self.client.get(reverse("review-json-pending-mine"))
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], mine.pk)

    def test_case_latest_returns_null_when_case_never_reviewed(self):
        user = UserFactory()
        _grant_all(user)
        self.client.force_login(user)

        case = TestCaseFactory()
        response = self.client.get(
            reverse("review-json-case-latest", args=[case.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["item"])

    def test_case_latest_returns_latest_review_item_for_case(self):
        user = UserFactory()
        _grant_all(user)
        self.client.force_login(user)

        case = TestCaseFactory()
        request = ReviewRequestFactory()
        ReviewItem.objects.create(
            review_request=request,
            case=case,
            decision=VoteDecision.APPROVED,
        )
        response = self.client.get(
            reverse("review-json-case-latest", args=[case.pk])
        )
        self.assertEqual(response.status_code, 200)
        item = response.json()["item"]
        self.assertEqual(item["decision"], VoteDecision.APPROVED)
        self.assertEqual(item["review_request"]["id"], request.pk)


class MissingTablesDefensiveTests(TestCase):
    """Regression guards — when the plugin's tables don't exist (e.g.
    migrations applied against the wrong DB), the views return a
    200 with an empty payload instead of 500. Simulates the missing-
    tables state by patching the ORM to raise DatabaseError.
    """

    def setUp(self):
        self.user = UserFactory()
        _grant_all(self.user)
        self.client.force_login(self.user)

    def test_pending_mine_returns_empty_on_database_error(self):
        with patch(
            "tcms_review.views.ReviewRequest.objects",
        ) as objects_mock:
            objects_mock.filter.side_effect = DatabaseError(
                'relation "tcms_review_reviewrequest" does not exist',
            )
            response = self.client.get(reverse("review-json-pending-mine"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"results": []})

    def test_case_latest_returns_null_on_database_error(self):
        with patch(
            "tcms_review.views.ReviewItem.objects",
        ) as objects_mock:
            objects_mock.filter.side_effect = DatabaseError(
                'relation "tcms_review_reviewitem" does not exist',
            )
            response = self.client.get(
                reverse("review-json-case-latest", args=[1])
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"item": None})

    def test_allowed_statuses_returns_empty_on_database_error(self):
        with patch(
            "tcms_review.views.get_allowed_case_statuses",
            side_effect=DatabaseError("no such table"),
        ):
            response = self.client.get(reverse("review-json-allowed-statuses"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"allowed": []})

    def test_list_view_renders_empty_on_database_error(self):
        with patch(
            "tcms_review.views.ReviewRequest.objects",
        ) as objects_mock:
            objects_mock.select_related.side_effect = DatabaseError(
                'relation "tcms_review_reviewrequest" does not exist',
            )
            # ReviewRequest.objects.none() still needs to work for the
            # fallback path — wire it up on the mock.
            objects_mock.none.return_value = ReviewRequest.objects.none()
            response = self.client.get(reverse("review-list"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["db_unavailable"])
