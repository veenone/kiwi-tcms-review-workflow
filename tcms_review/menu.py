from django.urls import reverse_lazy


# Appended to the MORE menu by Kiwi's plugin loader.
#
# A single "Test Review" parent with the request-oriented items first,
# then a divider, then the report hub. The old per-scope
# "Consolidated by product/testplan/testrun" entries were removed —
# they all land on the same /reports/ page with a scope query-param,
# which the Report hub exposes anyway as tabs.
#
# Divider convention: Kiwi renders the `("-", "-")` tuple as a
# <li class="divider">; see tcms/settings/common.py::MENU_ITEMS.
MENU_ITEMS = [
    ("Test Review", [
        ("All review requests", reverse_lazy("review-list")),
        ("New review request", reverse_lazy("review-new")),
        ("Review statistics", reverse_lazy("review-stats")),
        ("-", "-"),
        ("Report hub", reverse_lazy("review-report-hub")),
    ]),
]
