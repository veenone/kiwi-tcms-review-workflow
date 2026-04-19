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


class OutlineAdapter:
    """Uses Outline's documented REST API (https://getoutline.com/developers).

    Accepts either a collection UUID or a urlId slug (like
    'my-collection-DxNLmVSkhy') in `collection_id`. The slug is
    resolved to a UUID on first use via collections.info, because
    documents.create strictly requires the UUID form.
    """

    def __init__(self, base_url: str, api_token: str, collection_id: str):
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.collection_id = collection_id  # raw input (slug or UUID)
        self._resolved_uuid = None
        self.timeout = 10

    def _post(self, endpoint: str, payload: dict) -> dict:
        import requests  # noqa: WPS433

        url = f"{self.base_url}/api/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(
                url, headers=headers, data=json.dumps(payload), timeout=self.timeout,
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


class ConfluenceAdapter:
    """Uses Confluence Cloud REST API v2. Auth: email + API token (basic)."""

    def __init__(
        self, base_url: str, api_token: str, auth_email: str, space_key: str,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.auth_email = auth_email
        self.space_key = space_key
        self.timeout = 10

    def _request(self, method: str, path: str, payload: Optional[dict] = None) -> dict:
        import requests  # noqa: WPS433
        from requests.auth import HTTPBasicAuth  # noqa: WPS433

        url = f"{self.base_url}{path}"
        auth = HTTPBasicAuth(self.auth_email, self.api_token)
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"

        try:
            response = requests.request(
                method, url, headers=headers, auth=auth,
                data=json.dumps(payload) if payload else None,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise WikiSyncError(f"Confluence {path}: {exc}") from exc

        if response.status_code >= 400:
            raise WikiSyncError(
                f"Confluence {path}: HTTP {response.status_code} — "
                f"{response.text[:200]}"
            )
        if not response.text:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise WikiSyncError(f"Confluence {path}: invalid JSON: {exc}") from exc

    def _resolve_space_id(self) -> str:
        body = self._request("GET", f"/wiki/api/v2/spaces?keys={self.space_key}")
        results = body.get("results") or []
        if not results:
            raise WikiSyncError(f"Confluence space not found: {self.space_key}")
        return results[0]["id"]

    def test_connection(self) -> Optional[str]:
        body = self._request("GET", f"/wiki/api/v2/spaces?keys={self.space_key}")
        results = body.get("results") or []
        if not results:
            raise WikiSyncError(f"Space '{self.space_key}' not found or inaccessible")
        return results[0].get("name")

    def create_page(self, title: str, body_md: str) -> str:
        space_id = self._resolve_space_id()
        body = self._request("POST", "/wiki/api/v2/pages", {
            "spaceId": space_id,
            "status": "current",
            "title": title,
            "body": {"representation": "wiki", "value": body_md},
        })
        page_id = body.get("id")
        if not page_id:
            raise WikiSyncError("Confluence /pages create returned no id")
        return str(page_id)

    def update_page(self, page_id: str, body_md: str, append: bool = False) -> None:
        # v2 requires the current version number for updates; fetch it first.
        head = self._request("GET", f"/wiki/api/v2/pages/{page_id}")
        version = (head.get("version") or {}).get("number", 1)
        title = head.get("title", "Review")
        if append:
            existing_body = (
                (head.get("body") or {}).get("storage", {}).get("value", "")
            )
            body_md = existing_body + "\n\n" + body_md

        self._request("PUT", f"/wiki/api/v2/pages/{page_id}", {
            "id": page_id,
            "status": "current",
            "title": title,
            "body": {"representation": "wiki", "value": body_md},
            "version": {"number": version + 1, "message": "kiwitcms-review sync"},
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

    if config.backend == config.BACKEND_OUTLINE:
        if not config.api_token or not config.collection_id:
            return None
        return OutlineAdapter(
            base_url=config.base_url,
            api_token=config.api_token,
            collection_id=config.collection_id,
        )
    if config.backend == config.BACKEND_CONFLUENCE:
        if not config.api_token or not config.auth_email or not config.collection_id:
            return None
        return ConfluenceAdapter(
            base_url=config.base_url,
            api_token=config.api_token,
            auth_email=config.auth_email,
            space_key=config.collection_id,
        )
    return None
