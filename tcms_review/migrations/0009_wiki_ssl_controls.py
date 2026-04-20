"""Add verify_ssl and ca_bundle_path to WikiIntegrationConfig.

Operators hitting internal Outline / Confluence installs with
self-signed certs were getting ``SSL: CERTIFICATE_VERIFY_FAILED`` on
connection test and every sync call. The new fields let them either
point at a trusted CA bundle (preferred) or bypass verification when
the deployment context makes that acceptable.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tcms_review", "0008_wiki_integration"),
    ]

    operations = [
        migrations.AddField(
            model_name="historicalwikiintegrationconfig",
            name="verify_ssl",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Verify the wiki server's TLS certificate. Leave on "
                    "for public instances. Uncheck ONLY for internal "
                    "deployments with self-signed certs — doing so also "
                    "exposes you to MITM, so prefer providing a CA bundle "
                    "below instead."
                ),
            ),
        ),
        migrations.AddField(
            model_name="historicalwikiintegrationconfig",
            name="ca_bundle_path",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Absolute path to a PEM-encoded CA bundle the server "
                    "trusts. Use this for internal wikis instead of "
                    "disabling verification. Ignored when empty."
                ),
                max_length=512,
            ),
        ),
        migrations.AddField(
            model_name="wikiintegrationconfig",
            name="verify_ssl",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Verify the wiki server's TLS certificate. Leave on "
                    "for public instances. Uncheck ONLY for internal "
                    "deployments with self-signed certs — doing so also "
                    "exposes you to MITM, so prefer providing a CA bundle "
                    "below instead."
                ),
            ),
        ),
        migrations.AddField(
            model_name="wikiintegrationconfig",
            name="ca_bundle_path",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Absolute path to a PEM-encoded CA bundle the server "
                    "trusts. Use this for internal wikis instead of "
                    "disabling verification. Ignored when empty."
                ),
                max_length=512,
            ),
        ),
    ]
