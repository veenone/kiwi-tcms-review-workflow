from django.db import IntegrityError
from django.test import TestCase

from tcms.tests.factories import TestCaseFactory, UserFactory

from tcms_review.models import ReviewItem, ReviewVote
from tcms_review.state_machine import State, VoteDecision
from tcms_review.tests.factory import (
    ReviewItemFactory,
    ReviewRequestFactory,
    ReviewVoteFactory,
)


class ReviewRequestStrTests(TestCase):
    def test_str_contains_pk_and_title(self):
        request = ReviewRequestFactory(title="Audit payments")
        self.assertIn("Audit payments", str(request))
        self.assertIn(str(request.pk), str(request))


class RecalculateStateTests(TestCase):
    def test_stays_in_review_when_no_votes(self):
        request = ReviewRequestFactory(reviewers=[UserFactory(), UserFactory()])
        self.assertEqual(request.recalculate_state(), State.IN_REVIEW)

    def test_transitions_to_approved_when_all_reviewers_approve(self):
        reviewers = [UserFactory(), UserFactory()]
        request = ReviewRequestFactory(reviewers=reviewers)
        for user in reviewers:
            ReviewVoteFactory(
                review_request=request,
                reviewer=user,
                decision=VoteDecision.APPROVED,
            )
        request.refresh_from_db()
        self.assertEqual(request.state, State.APPROVED)

    def test_transitions_to_rejected_when_any_reviewer_rejects(self):
        reviewers = [UserFactory(), UserFactory()]
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
        request.refresh_from_db()
        self.assertEqual(request.state, State.REJECTED)

    def test_cancelled_requests_are_immutable(self):
        request = ReviewRequestFactory(
            reviewers=[UserFactory()],
            state=State.CANCELLED,
        )
        self.assertEqual(request.recalculate_state(), State.CANCELLED)


class UniqueConstraintTests(TestCase):
    def test_review_item_rejects_duplicate_case(self):
        request = ReviewRequestFactory()
        case = TestCaseFactory()
        ReviewItemFactory(review_request=request, case=case)
        with self.assertRaises(IntegrityError):
            ReviewItem.objects.create(review_request=request, case=case)

    def test_review_vote_rejects_duplicate_reviewer(self):
        request = ReviewRequestFactory()
        reviewer = UserFactory()
        ReviewVoteFactory(review_request=request, reviewer=reviewer)
        with self.assertRaises(IntegrityError):
            ReviewVote.objects.create(
                review_request=request,
                reviewer=reviewer,
                decision=VoteDecision.APPROVED,
            )
