from django.urls import reverse, reverse_lazy
from django.utils.functional import lazy


# Using lazy() rather than reverse_lazy + string concat, because the
# latter forces URL-resolution at module-load time (Kiwi imports this
# menu while settings are still being built).
def _hub_with_scope(scope):
    return reverse("review-report-hub") + f"?scope={scope}"


_hub_with_scope_lazy = lazy(_hub_with_scope, str)


# Appended to the MORE menu by Kiwi's plugin loader.
MENU_ITEMS = [
    ("Review Requests", [
        ("All review requests", reverse_lazy("review-list")),
        ("New review request", reverse_lazy("review-new")),
        ("Review statistics", reverse_lazy("review-stats")),
    ]),
    ("Review Reports", [
        ("Report hub", reverse_lazy("review-report-hub")),
        ("Consolidated by product", _hub_with_scope_lazy("product")),
        ("Consolidated by test plan", _hub_with_scope_lazy("testplan")),
        ("Consolidated by test run", _hub_with_scope_lazy("testrun")),
    ]),
]
