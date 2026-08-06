# Google Docs read/append, authenticated as the bot owner (OAuth refresh
# token minted once via scripts/google_oauth_setup.py — see that script for
# setup). Talks to the Docs REST API directly over httpx rather than pulling
# in google-api-python-client, keeping this a zero-new-dependency feature
# (httpx is already installed transitively via the anthropic SDK).
#
# Deliberately read/append only — no section-aware insertion. "Append to the
# end" covers "here's a link, add this info" cleanly without parsing the
# document's structural elements to guess where a heading-targeted insert
# should go.
import re
import time

import httpx

from claudefortelegram.config import settings

TOKEN_URL = "https://oauth2.googleapis.com/token"
DOCS_API_BASE = "https://docs.googleapis.com/v1/documents"

_DOC_ID_PATTERN = re.compile(r"/document/d/([a-zA-Z0-9_-]+)")

# Cached access token — refresh tokens don't expire from use, but the access
# token they mint is short-lived (~1h), so avoid re-minting one on every call.
_cached_access_token: str | None = None
_cached_expiry_monotonic: float = 0.0


def is_configured() -> bool:
    """False (the default) means the feature is simply off — the tools
    aren't added to the request and nothing else is affected."""
    return bool(settings.google_client_id and settings.google_client_secret and settings.google_refresh_token)


def extract_doc_id(url: str) -> str | None:
    match = _DOC_ID_PATTERN.search(url)
    return match.group(1) if match else None


async def _get_access_token() -> str:
    global _cached_access_token, _cached_expiry_monotonic
    if _cached_access_token and time.monotonic() < _cached_expiry_monotonic:
        return _cached_access_token

    async with httpx.AsyncClient() as http_client:
        response = await http_client.post(
            TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": settings.google_refresh_token,
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
        data = response.json()

    _cached_access_token = data["access_token"]
    # Refresh a bit before actual expiry rather than exactly at it.
    _cached_expiry_monotonic = time.monotonic() + data.get("expires_in", 3600) - 60
    return _cached_access_token


def _extract_text(document: dict) -> str:
    """Walk the Docs API's structural body.content list and pull out the
    plain text of every paragraph — enough for Claude to read and summarize,
    without trying to preserve formatting/tables/images."""
    parts = []
    for element in document.get("body", {}).get("content", []):
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        for run in paragraph.get("elements", []):
            text_run = run.get("textRun")
            if text_run:
                parts.append(text_run.get("content", ""))
    return "".join(parts)


async def _fetch_document(doc_id: str, token: str, http_client: httpx.AsyncClient) -> dict:
    response = await http_client.get(f"{DOCS_API_BASE}/{doc_id}", headers={"Authorization": f"Bearer {token}"})
    response.raise_for_status()
    return response.json()


async def read_doc(doc_id: str) -> str:
    token = await _get_access_token()
    async with httpx.AsyncClient() as http_client:
        document = await _fetch_document(doc_id, token, http_client)
    text = _extract_text(document)
    return text if text.strip() else "(the document is empty)"


async def append_to_doc(doc_id: str, text: str) -> None:
    token = await _get_access_token()
    async with httpx.AsyncClient() as http_client:
        document = await _fetch_document(doc_id, token, http_client)

        # Every Google Doc's body ends with an implicit trailing newline that
        # can't be deleted; its containing element's endIndex is the true
        # document length. The last valid insertion point is one before
        # that. Prefixing our text with "\n" puts it on its own new
        # paragraph rather than tacking it onto the existing last paragraph.
        end_index = document["body"]["content"][-1]["endIndex"] - 1
        insert_text = f"\n{text}" if end_index > 0 else text

        response = await http_client.post(
            f"{DOCS_API_BASE}/{doc_id}:batchUpdate",
            headers={"Authorization": f"Bearer {token}"},
            json={"requests": [{"insertText": {"location": {"index": end_index}, "text": insert_text}}]},
        )
        response.raise_for_status()
