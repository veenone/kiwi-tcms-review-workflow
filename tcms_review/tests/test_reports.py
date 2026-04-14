from datetime import timedelta

from django.test import TestCase

from tcms.tests.factories import TestCaseFactory, UserFactory

from tcms_review import reports
from tcms_review.models import ReviewItem
from tcms_review.state_machine import State, VoteDecision
from tcms_review.tests.factory import ReviewRequestFactory, ReviewVoteFactory


class ReportsTests(TestCase):
    def test_vote_breakdown_counts_each_decision(self):
        reviewers = [UserFactory(), UserFactory(), UserFactory()]
        request = ReviewRequestFactory(reviewers=reviewers)
        ReviewVoteFactory(
            review_request=request,
            reviewer=reviewers[0],
            decision=VoteDecision.APPROVED,
        )
        ReviewVoteFactory(
            review_request=request,
            reviewer=reviewers[1],
            decision=VoteDecision.REJECTED,
        )

        breakdown = reports.vote_breakdown(request)
        self.assertEqual(breakdown[VoteDecision.APPROVED], 1)
        self.assertEqual(breakdown[VoteDecision.REJECTED], 1)
        self.assertEqual(breakdown[VoteDecision.NEEDS_CHANGES], 0)

    def test_item_breakdown_counts_per_case_decisions(self):
        request = ReviewRequestFactory()
        ReviewItem.objects.create(
            review_request=request,
            case=TestCaseFactory(),
            decision=VoteDecision.APPROVED,
        )
        ReviewItem.objects.create(
            review_request=request,
            case=TestCaseFactory(),
            decision=ReviewItem.PENDING,
        )

        breakdown = reports.item_breakdown(request)
        self.assertEqual(breakdown.get(VoteDecision.APPROVED), 1)
        self.assertEqual(breakdown.get(ReviewItem.PENDING), 1)

    def test_time_to_decision_returns_none_when_not_terminal(self):
        request = ReviewRequestFactory(state=State.IN_REVIEW)
        self.assertIsNone(reports.time_to_decision(request))

    def test_time_to_decision_returns_delta_when_terminal(self):
        request = ReviewRequestFactory(state=State.APPROVED)
        result = reports.time_to_decision(request)
        self.assertIsInstance(result, timedelta)

    def test_participation_returns_zero_when_no_reviewers(self):
        request = ReviewRequestFactory()
        self.assertEqual(reports.participation(request), 0.0)

    def test_participation_returns_half_when_half_voted(self):
        reviewers = [UserFactory(), UserFactory()]
        request = ReviewRequestFactory(reviewers=reviewers)
        ReviewVoteFactory(
            review_request=request,
            reviewer=reviewers[0],
            decision=VoteDecision.APPROVED,
        )
        self.assertEqual(reports.participation(request), 0.5)
