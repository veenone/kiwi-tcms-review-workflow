"""factory_boy factories for tcms_review. Reuses Kiwi's factories for User/TestCase."""
import factory
from factory.django import DjangoModelFactory

from tcms.tests.factories import TestCaseFactory, UserFactory

from tcms_review.models import ReviewItem, ReviewRequest, ReviewVote
from tcms_review.state_machine import State, VoteDecision


class ReviewRequestFactory(DjangoModelFactory):
    class Meta:
        model = ReviewRequest

    title = factory.Sequence(lambda n: f"Review request {n}")
    description = "Default description"
    state = State.IN_REVIEW
    requester = factory.SubFactory(UserFactory)

    @factory.post_generation
    def reviewers(self, create, extracted, **kwargs):
        if not create:
            return
        if extracted:
            for user in extracted:
                self.reviewers.add(user)

    @factory.post_generation
    def cases(self, create, extracted, **kwargs):
        if not create:
            return
        if extracted:
            for case in extracted:
                ReviewItem.objects.create(review_request=self, case=case)


class ReviewItemFactory(DjangoModelFactory):
    class Meta:
        model = ReviewItem

    review_request = factory.SubFactory(ReviewRequestFactory)
    case = factory.SubFactory(TestCaseFactory)
    decision = ReviewItem.PENDING


class ReviewVoteFactory(DjangoModelFactory):
    class Meta:
        model = ReviewVote

    review_request = factory.SubFactory(ReviewRequestFactory)
    reviewer = factory.SubFactory(UserFactory)
    decision = VoteDecision.APPROVED
