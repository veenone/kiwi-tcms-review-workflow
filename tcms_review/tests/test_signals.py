from django.core import mail
from django.test import TestCase, override_settings

from tcms.tests.factories import UserFactory

from tcms_review.models import ReviewVote
from tcms_review.state_machine import State, VoteDecision
from tcms_review.tests.factory import ReviewRequestFactory


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class EmailSignalTests(TestCase):
    def setUp(self):
        mail.outbox = []

    def test_reviewers_receive_assigned_email_when_added_via_m2m(self):
        reviewer = UserFactory(email="reviewer@example.com")
        ReviewRequestFactory(reviewers=[reviewer])

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("reviewer@example.com", mail.outbox[0].to)

    def test_requester_receives_state_changed_email_on_transition(self):
        requester = UserFactory(email="requester@example.com")
        reviewers = [UserFactory(), UserFactory()]
        request = ReviewRequestFactory(requester=requester, reviewers=reviewers)
        mail.outbox = []  # Drop the assigned.txt emails

        # Force a state transition by casting REJECTED
        ReviewVote.objects.create(
            review_request=request,
            reviewer=reviewers[0],
            decision=VoteDecision.REJECTED,
        )

        request.refresh_from_db()
        self.assertEqual(request.state, State.REJECTED)
        requester_messages = [m for m in mail.outbox if "requester@example.com" in m.to]
        self.assertTrue(len(requester_messages) >= 1)

    def test_requester_receives_vote_cast_email(self):
        requester = UserFactory(email="requester@example.com")
        reviewer = UserFactory(email="reviewer@example.com")
        request = ReviewRequestFactory(requester=requester, reviewers=[reviewer])
        mail.outbox = []

        ReviewVote.objects.create(
            review_request=request,
            reviewer=reviewer,
            decision=VoteDecision.APPROVED,
        )

        requester_messages = [m for m in mail.outbox if "requester@example.com" in m.to]
        self.assertTrue(len(requester_messages) >= 1)

    def test_no_state_email_when_state_did_not_change(self):
        requester = UserFactory(email="requester@example.com")
        request = ReviewRequestFactory(requester=requester, reviewers=[UserFactory()])
        mail.outbox = []

        # Save with no state change
        request.title = "Updated title"
        request.save()

        state_mails = [m for m in mail.outbox if "now" in m.subject]
        self.assertEqual(len(state_mails), 0)
