"""XML-RPC methods. Auto-discovered by modernrpc once apps.py registers
this module on MODERNRPC_METHODS_MODULES at startup.

Skeleton — flesh out per the build sequence in the plan.
"""
from modernrpc.core import rpc_method
from tcms.rpc.decorators import permissions_required


@permissions_required("tcms_review.view_reviewrequest")
@rpc_method(name="ReviewRequest.filter")
def filter_requests(query=None):
    from django.forms.models import model_to_dict
    from tcms_review.models import ReviewRequest

    qs = ReviewRequest.objects.filter(**(query or {}))
    return [model_to_dict(r) for r in qs]
