"""Grant tcms_review.* permissions to Kiwi groups.

Operator-invokable recovery tool. Runs the same grant logic as the
post_migrate signal handler in apps.py, but usable any time — e.g.
after fixing a broken django_content_type schema, or to extend access
to groups beyond the Tester/Administrator defaults.

Usage::

    ./manage.py tcms_review_grant_perms
    ./manage.py tcms_review_grant_perms --group Tester --group Leader

Exits non-zero if no tcms_review.* Permission rows exist (= migrations
haven't been applied against the connected DB).
"""
from django.core.management.base import BaseCommand, CommandError

from tcms_review.permissions import (
    DEFAULT_GROUPS,
    get_app_permissions,
    grant_permissions_to_groups,
)


class Command(BaseCommand):
    help = (
        "Grant tcms_review.* permissions to Kiwi groups. Defaults to "
        "Tester and Administrator; override with one or more --group "
        "flags."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--group",
            action="append",
            dest="groups",
            metavar="NAME",
            help=(
                "Group name to grant permissions to. Repeat the flag for "
                f"multiple groups. Default: {', '.join(DEFAULT_GROUPS)}."
            ),
        )

    def handle(self, *args, **options):
        groups = tuple(options.get("groups") or DEFAULT_GROUPS)

        app_perms = get_app_permissions()
        if not app_perms:
            raise CommandError(
                "No tcms_review.* permissions exist in the database. "
                "Run './manage.py migrate tcms_review' first. If the "
                "migration completed but permissions are still missing, "
                "check django_content_type for a stale schema (see the "
                "README Troubleshooting section)."
            )

        summary = grant_permissions_to_groups(groups)

        granted_any = False
        for name, count in summary.items():
            if count:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Granted {count} permissions to group '{name}'."
                    ),
                )
                granted_any = True
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"Group '{name}' not found — skipped."
                    ),
                )

        if not granted_any:
            raise CommandError(
                "No groups matched; nothing granted. Use --group NAME "
                "to target a group that actually exists."
            )
