import base64
import json
import logging
import os
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError  # noqa: F401 — re-exported for callers

from maildrain.models import RawMessage

logger = logging.getLogger(__name__)

# gmail.insert  — upload messages
# gmail.labels  — read and create labels (needed to apply labels on upload)
SCOPES = [
    "https://www.googleapis.com/auth/gmail.insert",
    "https://www.googleapis.com/auth/gmail.labels",
]


# ---------------------------------------------------------------------------
# Secret Manager helpers (used when GOOGLE_TOKEN_SECRET is set)
# ---------------------------------------------------------------------------


def _sm_client() -> Any:
    from google.cloud import secretmanager

    return secretmanager.SecretManagerServiceClient()


def _read_token_from_secret(secret_name: str) -> str | None:
    """
    Fetch the token JSON string from Secret Manager.
    Returns None if the secret has no accessible versions yet.
    """
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        raise OSError(
            "GOOGLE_CLOUD_PROJECT must be set when GOOGLE_TOKEN_SECRET is configured."
        )
    client = _sm_client()
    resource = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    try:
        response = client.access_secret_version(name=resource)
        return str(response.payload.data.decode("utf-8"))
    except Exception:
        return None


def _write_token_to_secret(secret_name: str, token_json: str) -> None:
    """
    Add a new version of the token secret in Secret Manager, then disable all
    previous enabled versions so the version_destroy_ttl policy can clean them up.
    """
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    client = _sm_client()
    parent = f"projects/{project_id}/secrets/{secret_name}"

    new_version = client.add_secret_version(
        request={
            "parent": parent,
            "payload": {"data": token_json.encode("utf-8")},
        }
    )

    for version in client.list_secret_versions(
        request={"parent": parent, "filter": "state=ENABLED"}
    ):
        if version.name != new_version.name:
            client.disable_secret_version(request={"name": version.name})
            logger.info(
                "Disabled old token secret version: %s", version.name.split("/")[-1]
            )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def get_credentials(
    credentials_file: str,
    token_file: str,
    token_secret: str | None = None,
) -> Credentials:
    """
    Load cached OAuth credentials.

    When token_secret is set, reads the token from Secret Manager and writes
    any updated token back as a new secret version. This is the GCP path.

    When token_secret is not set, reads from / writes to token_file on disk.
    This is the local development path.

    Refreshes silently if the access token is expired and a refresh token is
    available. Runs the interactive browser-based OAuth flow if no valid
    credentials exist at all (local dev only — not possible on Cloud Run).
    """
    creds: Credentials | None = None

    if token_secret:
        token_json = _read_token_from_secret(token_secret)
        if token_json:
            creds = Credentials.from_authorized_user_info(  # type: ignore[no-untyped-call]  # google-auth class method lacks annotations
                json.loads(token_json), SCOPES
            )
    elif Path(token_file).exists():
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)  # type: ignore[no-untyped-call]  # google-auth class method lacks annotations

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            old_refresh_token = creds.refresh_token
            creds.refresh(Request())
            # Only persist if the refresh token changed — access tokens are ephemeral
            # and don't need to be stored. Refresh tokens rotate rarely.
            token_changed = creds.refresh_token != old_refresh_token
        else:
            if not Path(credentials_file).exists():
                raise FileNotFoundError(
                    f"Google OAuth credentials file not found: {credentials_file!r}\n"
                    "Download it from Google Cloud Console > APIs & Services > Credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
            token_changed = True

        assert creds is not None
        if token_changed:
            if token_secret:
                _write_token_to_secret(token_secret, creds.to_json())  # type: ignore[no-untyped-call]  # google-auth method lacks annotations
            else:
                with open(token_file, "w") as f:
                    f.write(creds.to_json())  # type: ignore[no-untyped-call]  # google-auth method lacks annotations

    assert creds is not None
    return creds


def build_gmail_service(
    credentials_file: str,
    token_file: str,
    token_secret: str | None = None,
) -> Any:
    """Return an authenticated Gmail API service object."""
    creds = get_credentials(credentials_file, token_file, token_secret)
    return build("gmail", "v1", credentials=creds)


# ---------------------------------------------------------------------------
# Label helpers
# ---------------------------------------------------------------------------


def resolve_label_ids(service: Any, label_names: list[str]) -> list[str]:
    """
    Resolve a list of label names to their Gmail label IDs, creating any
    that don't already exist.

    Returns a list of label ID strings in the same order as label_names.
    Raises googleapiclient.errors.HttpError on API failure.
    """
    if not label_names:
        return []

    existing = service.users().labels().list(userId="me").execute().get("labels", [])
    name_to_id = {lbl["name"]: lbl["id"] for lbl in existing}

    ids: list[str] = []
    for name in label_names:
        if name in name_to_id:
            ids.append(name_to_id[name])
        else:
            created = (
                service.users()
                .labels()
                .create(
                    userId="me",
                    body={"name": name},
                )
                .execute()
            )
            ids.append(created["id"])
            name_to_id[name] = created["id"]
            logger.info("Created label %r (id: %s)", name, created["id"])

    return ids


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


def upload_message(
    service: Any, raw_message: RawMessage, label_ids: list[str] | None = None
) -> str:
    """
    Upload a single RFC 2822 message to Gmail using messages.insert.

    Uses internalDateSource='dateHeader' so Gmail respects the original
    Date: header for ordering rather than the import timestamp.

    If label_ids is provided, those labels are applied to the message in
    addition to the standard INBOX and UNREAD system labels.

    Returns the Gmail message ID string on success.
    Raises googleapiclient.errors.HttpError on failure.
    """
    encoded = base64.urlsafe_b64encode(raw_message.raw_bytes).decode("ascii")
    body: dict[str, Any] = {"raw": encoded}
    if label_ids:
        body["labelIds"] = ["INBOX", "UNREAD", *label_ids]
    result = (
        service.users()
        .messages()
        .insert(
            userId="me",
            body=body,
            internalDateSource="dateHeader",
        )
        .execute()
    )
    return str(result["id"])
