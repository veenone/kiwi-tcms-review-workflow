"""Pure unit tests for the state machine. No Django, no DB — runs anywhere."""
import unittest

from tcms_review.state_machine import State, VoteDecision, VoteSnapshot, transition


class TransitionTests(unittest.TestCase):
    def test_should_stay_in_review_when_no_votes(self):
        self.assertEqual(transition(reviewer_count=2, votes=[]), State.IN_REVIEW)

    def test_should_stay_in_review_when_some_reviewers_have_not_voted(self):
        votes = [VoteSnapshot(reviewer_id=1, decision=VoteDecision.APPROVED)]
        self.assertEqual(transition(reviewer_count=2, votes=votes), State.IN_REVIEW)

    def test_should_return_approved_when_all_reviewers_approve(self):
        votes = [
            VoteSnapshot(reviewer_id=1, decision=VoteDecision.APPROVED),
            VoteSnapshot(reviewer_id=2, decision=VoteDecision.APPROVED),
        ]
        self.assertEqual(transition(reviewer_count=2, votes=votes), State.APPROVED)

    def test_should_return_rejected_when_any_reviewer_rejects(self):
        votes = [
            VoteSnapshot(reviewer_id=1, decision=VoteDecision.APPROVED),
            VoteSnapshot(reviewer_id=2, decision=VoteDecision.REJECTED),
        ]
        self.assertEqual(transition(reviewer_count=2, votes=votes), State.REJECTED)

    def test_should_return_changes_requested_when_any_needs_changes(self):
        votes = [
            VoteSnapshot(reviewer_id=1, decision=VoteDecision.APPROVED),
            VoteSnapshot(reviewer_id=2, decision=VoteDecision.NEEDS_CHANGES),
        ]
        self.assertEqual(transition(reviewer_count=2, votes=votes), State.CHANGES_REQUESTED)

    def test_rejected_takes_precedence_over_needs_changes(self):
        votes = [
            VoteSnapshot(reviewer_id=1, decision=VoteDecision.NEEDS_CHANGES),
            VoteSnapshot(reviewer_id=2, decision=VoteDecision.REJECTED),
        ]
        self.assertEqual(transition(reviewer_count=2, votes=votes), State.REJECTED)


if __name__ == "__main__":
    unittest.main()
