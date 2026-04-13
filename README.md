# kiwitcms-review

Test case review workflow plugin for [Kiwi TCMS](https://kiwitcms.org/).

Group test cases into a **Review Request**, assign reviewers, collect their decisions, and notify by email — all without modifying Kiwi TCMS core. Auto-discovered as a Kiwi plugin via the `kiwitcms.plugins` entry point.

## Features

- **Review Request** — group one or more `TestCase` objects into a single review cycle with title, description, due date, and a state machine
- **Per-reviewer votes** — `Approved` / `Needs changes` / `Rejected`
- **Per-case decisions** — track approval status for each case in the request
- **Automatic state transitions** — request transitions to `Approved` / `Rejected` / `Changes requested` once votes are in
- **Email notifications** — reviewers notified on assignment, requester notified on votes and state changes (uses `tcms.core.utils.mailto`)
- **Dashboard widget** — "Pending my review" panel injected into the Kiwi dashboard
- **"Send for review" button** — injected into TestCase / TestPlan detail pages via JS (no template overrides → survives Kiwi upgrades)
- **XML-RPC API** — `ReviewRequest.create`, `ReviewVote.cast`, `ReviewRequest.metrics`, etc.
- **Per-session reporting** — vote breakdown, time-to-decision, reviewer participation
- **Audit trail** — `KiwiHistoricalRecords` on every model

## Installation

```bash
pip install kiwitcms-review
./manage.py makemigrations tcms_review   # first install only
./manage.py migrate tcms_review
./manage.py collectstatic --noinput
```

That's it. Kiwi auto-discovers the plugin via the `kiwitcms.plugins` entry point and:

- adds `tcms_review` to `INSTALLED_APPS`
- mounts the URLs at `/reviews/`
- adds the menu items to the **MORE** menu
- registers the XML-RPC methods (done in `apps.py::ready()`)

## Permissions

Two Django permissions are added on first migrate:

- `tcms_review.add_reviewrequest` — can create review requests
- `tcms_review.change_reviewrequest` — required to be a reviewer / cast votes

Both are auto-granted to the built-in `Tester` group.

## Compatibility

- Kiwi TCMS ≥ 12.0
- Python ≥ 3.9
- Django ≥ 3.2

## License

GPL-2.0-or-later
