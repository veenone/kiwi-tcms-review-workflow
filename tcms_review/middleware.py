"""Response-rewriting middleware that injects the plugin's JS bundle into
every HTML response.

This is how the plugin reaches Kiwi core pages without editing any core
template. The middleware is registered from apps.py::ready() so there's
nothing for the operator to do at install time beyond running `migrate`.

The injected bundle (static/tcms_review/js/inject.js) is self-contained;
it detects the page via body[id] and no-ops on pages it doesn't know
about, so the middleware can run safely on every HTML response.
"""


class InjectReviewBundleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

        # Build the script tag once at middleware-construction time so the
        # hot path is a single byte-level replace. STATIC_URL is available
        # by this point because middleware is instantiated after settings
        # have been fully loaded.
        from django.templatetags.static import static  # noqa: WPS433

        url = static("tcms_review/js/inject.js")
        self.script_tag = (
            f'<script src="{url}" defer data-source="tcms_review"></script>'
        ).encode("utf-8")

    def __call__(self, request):
        response = self.get_response(request)

        # Skip streaming responses (SSE, file downloads, etc.) — touching
        # response.content on a StreamingHttpResponse raises.
        if getattr(response, "streaming", False):
            return response

        content_type = response.get("Content-Type", "")
        if not content_type.startswith("text/html"):
            return response

        content = getattr(response, "content", None)
        if not content or b"</body>" not in content:
            return response

        # Idempotent: don't double-inject if another middleware or view
        # somehow re-triggers us (e.g. server-side includes).
        if self.script_tag in content:
            return response

        response.content = content.replace(
            b"</body>", self.script_tag + b"</body>", 1,
        )
        if response.has_header("Content-Length"):
            response["Content-Length"] = str(len(response.content))
        return response
