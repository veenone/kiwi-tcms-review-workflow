from django.urls import reverse_lazy

# Appended to the MORE menu by Kiwi's plugin loader.
MENU_ITEMS = [
    ("Review Requests", [
        ("All review requests", reverse_lazy("review-list")),
        ("New review request", reverse_lazy("review-new")),
        ("Review statistics", reverse_lazy("review-stats")),
    ]),
]
