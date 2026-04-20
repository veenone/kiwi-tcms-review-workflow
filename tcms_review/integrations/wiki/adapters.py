"""Wiki adapters — one class per supported backend.

All adapters share a small interface so the caller (signal handler)
doesn't care which wiki is on the other end.

Every adapter's HTTP calls have short timeouts and swallow errors into
a domain-specific WikiSyncError so the signal handler can log-and-move-on
without blocking the review workflow.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

logger = logging.getLogger("tcms_review.wiki")


class WikiSyncError(Exception):
    """Raised when the wiki adapter can't create/update/close a page."""


import re

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _suppress_insecure_warning_if_unverified(verify):
    """urllib3 spams a warning on every verify=False call. Operators
    who chose to disable verification have already accepted the risk;
    silence the repeat noise so logs stay readable."""
    if verify is False:
        try:
            import urllib3  # noqa: WPS433

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:  # noqa: BLE001
            pass


class OutlineAdapter:
    """Uses Outline's documented REST API (https://getoutline.com/developers).

    Accepts either a collection UUID or a urlId slug (like
    'my-collection-DxNLmVSkhy') in `collection_id`. The slug is
    resolved to a UUID on first use via collections.info, because
    documents.create strictly requires the UUID form.
    """

    def __init__(self, base_url: str, api_token: str, collection_id: str, verify=True):
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.collection_id = collection_id  # raw input (slug or UUID)
        self._resolved_uuid = None
        self.timeout = 10
        # Either True/False or the path to a CA bundle, following the
        # shape requests' `verify=` argument expects.
        self.verify = verify
        _suppress_insecure_warning_if_unverified(verify)

    def _post(self, endpoint: str, payload: dict) -> dict:
        import requests  # noqa: WPS433

        url = f"{self.base_url}/api/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(
                url,
                headers=headers,
                data=json.dumps(payload),
                timeout=self.timeout,
                verify=self.verify,
            )
        except requests.RequestException as exc:
            raise WikiSyncError(f"Outline {endpoint}: {exc}") from exc

        if response.status_code >= 400:
            raise WikiSyncError(
                f"Outline {endpoint}: HTTP {response.status_code} — "
                f"{response.text[:200]}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise WikiSyncError(f"Outline {endpoint}: invalid JSON: {exc}") from exc

    def _resolve_collection_uuid(self) -> str:
        """Resolve the stored collection_id (UUID or slug) to a UUID.
        Cached on first call."""
        if self._resolved_uuid:
            return self._resolved_uuid

        if _UUID_RE.match(self.collection_id):
            self._resolved_uuid = self.collection_id
            return self._resolved_uuid

        # Treat as urlId slug — ask collections.info, which accepts both
        body = self._post("collections.info", {"id": self.collection_id})
        data = body.get("data") or {}
        uuid = data.get("id")
        if not uuid or not _UUID_RE.match(uuid):
            raise WikiSyncError(
                f"Outline collections.info returned no UUID for "
                f"'{self.collection_id}'"
            )
        self._resolved_uuid = uuid
        return uuid

    def test_connection(self) -> Optional[str]:
        """Return the collection name if credentials work, else raise."""
        body = self._post("collections.info", {"id": self.collection_id})
        data = body.get("data") or {}
        # Opportunistically cache the UUID since we already have it.
        uuid = data.get("id")
        if uuid and _UUID_RE.match(uuid):
            self._resolved_uuid = uuid
        return data.get("name")

    def create_page(self, title: str, body_md: str) -> str:
        body = self._post("documents.create", {
            "title": title,
            "text": body_md,
            "collectionId": self._resolve_collection_uuid(),
            "publish": True,
        })
        doc_id = (body.get("data") or {}).get("id")
        if not doc_id:
            raise WikiSyncError("Outline documents.create returned no id")
        return doc_id

    def update_page(self, page_id: str, body_md: str, append: bool = False) -> None:
        self._post("documents.update", {
            "id": page_id,
            "text": body_md,
            "append": bool(append),
            "publish": True,
        })

    def close_page(self, page_id: str) -> None:
        # Outline has no "closed" state; we append a trailing marker and
        # leave archival to the operator.
        self.update_page(
            page_id,
            body_md="\n\n---\n**Status:** Closed (review terminal state)\n",
            append=True,
        )


def _markdown_to_confluence_html(body_md: str) -> str:
    """Render markdown as XHTML suitable for Confluence 'storage' format.

    Confluence's wiki representation is NOT markdown — it uses its own
    syntax (`h1.`, `*`, etc). Safer to convert to HTML server-side and
    send as `storage`, which Confluence accepts on both Cloud and DC.

    Uses the `markdown` package if available (pulled in by Kiwi TCMS
    itself). Falls back to a minimal wrap if not."""
    try:
        import markdown  # noqa: WPS433
    except ImportError:
        # Escape and preserve line breaks so the page at least shows
        # readable content instead of raw syntax characters.
        from html import escape  # noqa: WPS433
        return "<pre>" + escape(body_md) + "</pre>"

    return markdown.markdown(
        body_md,
        extensions=["extra", "tables", "fenced_code"],
        output_format="html",
    )


class ConfluenceAdapter:
    """Confluence REST client that works for both Cloud and Data Center.

    Uses the v1 REST API (`/rest/api/content/*`) which is available on
    every supported Confluence flavour. The v2 API (`/wiki/api/v2/*`)
    is Cloud-only and would block Data Center customers.

    Authentication auto-detection:
    - If `auth_email` is set → HTTP Basic with (auth_email, api_token).
      This covers Atlassian Cloud (email + API token) and DC instances
      that accept basic auth with username + PAT.
    - If `auth_email` is empty → `Authorization: Bearer <api_token>`.
      This is the DC Personal Access Token flow.

    Base URL examples:
    - Cloud: `https://your-org.atlassian.net/wiki`
    - DC:    `https://confluence.example.com`

    Body: we render markdown to HTML and send as `representation: storage`
    (Confluence XHTML). This renders cleanly on both flavours without
    depending on the fragile `wiki` representation.
    """

    def __init__(
        self, base_url: str, api_token: str, auth_email: str, space_key: str,
        verify=True,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.auth_email = (auth_email or "").strip()
        self.space_key = space_key
        self.timeout = 10
        self.verify = verify
        _suppress_insecure_warning_if_unverified(verify)

    def _api_path(self, suffix: str) -> str:
        """Compose `/rest/api/{suffix}` or `/wiki/rest/api/{suffix}` depending
        on whether the base URL already ends in `/wiki`."""
        if self.base_url.endswith("/wiki"):
            return f"/rest/api/{suffix.lstrip('/')}"
        # DC or Cloud URL without the /wiki suffix
        return f"/rest/api/{suffix.lstrip('/')}"

    def _request(self, method: str, path: str, payload: Optional[dict] = None) -> dict:
        import requests  # noqa: WPS433

        url = f"{self.base_url}{path}"
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"

        auth = None
        if self.auth_email:
            from requests.auth import HTTPBasicAuth  # noqa: WPS433
            auth = HTTPBasicAuth(self.auth_email, self.api_token)
        else:
            # DC Personal Access Token flow
            headers["Authorization"] = f"Bearer {self.api_token}"

        try:
            response = requests.request(
                method, url, headers=headers, auth=auth,
                data=json.dumps(payload) if payload else None,
                timeout=self.timeout,
                verify=self.verify,
            )
        except requests.RequestException as exc:
            raise WikiSyncError(f"Confluence {path}: {exc}") from exc

        if response.status_code >= 400:
            raise WikiSyncError(
                f"Confluence {path}: HTTP {response.status_code} — "
                f"{response.text[:250]}"
            )
        if not response.text:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise WikiSyncError(f"Confluence {path}: invalid JSON: {exc}") from exc

    def test_connection(self) -> Optional[str]:
        """Probe /rest/api/space/{KEY} — identical response shape on
        Cloud and Data Center. Returns the space name."""
        body = self._request(
            "GET", self._api_path(f"space/{self.space_key}?expand=description"),
        )
        name = body.get("name")
        if not name:
            raise WikiSyncError(
                f"Space '{self.space_key}' not found or inaccessible"
            )
        return name

    def create_page(self, title: str, body_md: str) -> str:
        html_body = _markdown_to_confluence_html(body_md)
        body = self._request("POST", self._api_path("content"), {
            "type": "page",
            "title": title,
            "space": {"key": self.space_key},
            "body": {
                "storage": {
                    "value": html_body,
                    "representation": "storage",
                },
            },
        })
        page_id = body.get("id")
        if not page_id:
            raise WikiSyncError("Confluence POST /content returned no id")
        return str(page_id)

    def update_page(self, page_id: str, body_md: str, append: bool = False) -> None:
        # v1 requires the current version number for updates; fetch first.
        head = self._request(
            "GET",
            self._api_path(f"content/{page_id}?expand=body.storage,version"),
        )
        version = (head.get("version") or {}).get("number", 1)
        title = head.get("title", "Review")

        new_html = _markdown_to_confluence_html(body_md)
        if append:
            existing_html = (
                ((head.get("body") or {}).get("storage") or {}).get("value", "")
            )
            merged_html = existing_html + "\n" + new_html
        else:
            merged_html = new_html

        self._request("PUT", self._api_path(f"content/{page_id}"), {
            "id": page_id,
            "type": "page",
            "title": title,
            "space": {"key": self.space_key},
            "body": {
                "storage": {
                    "value": merged_html,
                    "representation": "storage",
                },
            },
            "version": {
                "number": version + 1,
                "message": "kiwitcms-review sync",
            },
        })

    def close_page(self, page_id: str) -> None:
        self.update_page(
            page_id,
            body_md="\n\n---\n**Status:** Closed (review terminal state)\n",
            append=True,
        )


def get_adapter(config):
    """Factory: picks the right adapter for a WikiIntegrationConfig row.
    Returns None when disabled / not configured."""
    if not config or not config.is_enabled:
        return None

    verify = getattr(config, "requests_verify", True)

    if config.backend == config.BACKEND_OUTLINE:
        if not config.api_token or not config.collection_id:
            return None
        return OutlineAdapter(
            base_url=config.base_url,
            api_token=config.api_token,
            collection_id=config.collection_id,
            verify=verify,
        )
    if config.backend == config.BACKEND_CONFLUENCE:
        if not config.api_token or not config.auth_email or not config.collection_id:
            return None
        return ConfluenceAdapter(
            base_url=config.base_url,
            api_token=config.api_token,
            auth_email=config.auth_email,
            space_key=config.collection_id,
            verify=verify,
        )
    return None
