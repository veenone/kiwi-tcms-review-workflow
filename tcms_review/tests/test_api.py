"""XML-RPC handler unit tests. These call the RPC functions directly
(passing a synthetic request object in kwargs) rather than going through
an HTTP fixture — much faster and sufficient for the business logic.
"""
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from modernrpc.core import REQUEST_KEY

from tcms.tests.factories import TestCaseFactory, UserFactory

from tcms_review import api
from tcms_review.models import ReviewItem, ReviewRequest, ReviewVote
from tcms_review.state_machine import State, VoteDecision
from tcms_review.tests.factory import (
    ReviewItemFactory,
    ReviewRequestFactory,
    ReviewVoteFactory,
)


def _rpc_kwargs(user):
    rf = RequestFactory()
    request = rf.get("/")
    request.user = user
    return {REQUEST_KEY: request}


def _grant(user, *codenames):
    user.user_permissions.add(
        *Permission.objects.filter(codename__in=codenames)
    )


class ReviewRequestAPITests(TestCase):
    def test_create_returns_dict_and_sets_requester(self):
        user = UserFactory()
        _grant(user, "add_reviewrequest")
        reviewer = UserFactory()

        result = api.create(
            {
                "title": "API review",
                "description": "",
                "due_date": None,
                "reviewers": [reviewer.pk],
            },
            **_rpc_kwargs(user),
        )

        self.assertEqual(result["title"], "API review")
        request = ReviewRequest.objects.get(pk=result["id"])
        self.assertEqual(request.requester, user)

    def test_create_raises_value_error_on_missing_reviewers(self):
        user = UserFactory()
        _grant(user, "add_reviewrequest")

        with self.assertRaises(ValueError):
            api.create(
                {"title": "Missing reviewers", "description": "", "due_date": None, "reviewers": []},
                **_rpc_kwargs(user),
            )

    def test_filter_returns_matching_rows(self):
        ReviewRequestFactory(title="First")
        ReviewRequestFactory(title="Second")

        result = api.filter_requests({"title": "First"})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "First")

    def test_cancel_rejects_non_requester(self):
        owner = UserFactory()
        stranger = UserFactory()
        request = ReviewRequestFactory(requester=owner)

        with self.assertRaises(PermissionDenied):
            api.cancel(request.pk, **_rpc_kwargs(stranger))

    def test_cancel_succeeds_for_requester(self):
        owner = UserFactory()
        request = ReviewRequestFactory(requester=owner)

        result = api.cancel(request.pk, **_rpc_kwargs(owner))
        self.assertEqual(result["state"], State.CANCELLED)


class ReviewVoteAPITests(TestCase):
    def test_cast_rejects_non_reviewer(self):
        stranger = UserFactory()
        request = ReviewRequestFactory()

        with self.assertRaises(PermissionDenied):
            api.cast_vote(
                request.pk,
                VoteDecision.APPROVED,
                **_rpc_kwargs(stranger),
            )

    def test_cast_rejects_vote_on_cancelled_request(self):
        reviewer = UserFactory()
        request = ReviewRequestFactory(
            reviewers=[reviewer],
            state=State.CANCELLED,
        )

        with self.assertRaises(PermissionDenied):
            api.cast_vote(
                request.pk,
                VoteDecision.APPROVED,
                **_rpc_kwargs(reviewer),
            )

    def test_cast_creates_vote_and_recalculates_state(self):
        reviewer = UserFactory()
        request = ReviewRequestFactory(reviewers=[reviewer])

        result = api.cast_vote(
            request.pk,
            VoteDecision.APPROVED,
            comment="lgtm",
            **_rpc_kwargs(reviewer),
        )

        self.assertEqual(result["decision"], VoteDecision.APPROVED)
        request.refresh_from_db()
        self.assertEqual(request.state, State.APPROVED)

    def test_cast_raises_value_error_on_invalid_decision(self):
        reviewer = UserFactory()
        request = ReviewRequestFactory(reviewers=[reviewer])

        with self.assertRaises(ValueError):
            api.cast_vote(
                request.pk,
                "not-a-decision",
                **_rpc_kwargs(reviewer),
            )


class ReviewItemAPITests(TestCase):
    def test_set_decision_updates_item(self):
        item = ReviewItemFactory()
        api.set_item_decision(item.pk, VoteDecision.APPROVED, comment="passes")
        item.refresh_from_db()
        self.assertEqual(item.decision, VoteDecision.APPROVED)

    def test_set_decision_raises_on_invalid_value(self):
        item = ReviewItemFactory()
        with self.assertRaises(ValueError):
            api.set_item_decision(item.pk, "bogus")

    def test_filter_returns_items_ordered_by_updated_at(self):
        case = TestCaseFactory()
        item = ReviewItemFactory(case=case)

        result = api.filter_items({"case": case.pk})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], item.pk)


class MetricsAPITests(TestCase):
    def test_metrics_returns_wire_friendly_dict(self):
        request = ReviewRequestFactory(state=State.APPROVED)
        result = api.metrics(request.pk)

        self.assertEqual(result["state"], State.APPROVED)
        self.assertIn("votes", result)
        self.assertIn("items", result)
        self.assertIn("time_to_decision_seconds", result)
