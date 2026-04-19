"""Response-rewriting middleware that injects the plugin's JS bundle into
every HTML response.

This is how the plugin reaches Kiwi core pages without editing any core
template. The middleware is registered from apps.py::ready() so there's
nothing for the operator to do at install time beyond running `migrate`.

The injected bundle (static/tcms_review/js/inject.js) is self-contained;
it detects the page via body[id] and no-ops on pages it doesn't know
about, so the middleware can run safely on every HTML response.

Since v0.7.0 the tag also carries a `data-current-user-id` attribute so
the JS can decide whether to show author-only affordances (e.g. the
"Send for review" button only renders for the TestCase author).
"""


class InjectReviewBundleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

        # Build the script URL once at middleware-construction time.
        # STATIC_URL is available by this point because middleware is
        # instantiated after settings have been fully loaded.
        from django.templatetags.static import static  # noqa: WPS433

        from tcms_review import __version__  # noqa: WPS433

        url = static("tcms_review/js/inject.js")
        # Append plugin version as a cache-buster. Changes on every release
        # so browsers pick up updated JS without a hard refresh.
        self._versioned_src = f"{url}?v={__version__}"

    def _script_tag(self, request):
        """Build the script tag with per-request user context."""
        user = getattr(request, "user", None)
        user_id = ""
        if user is not None and user.is_authenticated:
            user_id = str(user.pk)
        tag = (
            f'<script src="{self._versioned_src}" defer '
            f'data-source="tcms_review" '
            f'data-current-user-id="{user_id}"></script>'
        )
        return tag.encode("utf-8")

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

        script_tag = self._script_tag(request)

        # Idempotent: don't double-inject if another middleware or view
        # somehow re-triggers us (e.g. server-side includes).
        if b'data-source="tcms_review"' in content:
            return response

        response.content = content.replace(
            b"</body>", script_tag + b"</body>", 1,
        )
        if response.has_header("Content-Length"):
            response["Content-Length"] = str(len(response.content))
        return response
