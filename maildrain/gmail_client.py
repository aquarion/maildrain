import base64
import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError  # noqa: F401 — re-exported for callers

from maildrain.models import RawMessage

# gmail.insert  — upload messages
# gmail.labels  — read and create labels (needed to apply labels on upload)
SCOPES = [
    "https://www.googleapis.com/auth/gmail.insert",
    "https://www.googleapis.com/auth/gmail.labels",
]


# ---------------------------------------------------------------------------
# Secret Manager helpers (used when GOOGLE_TOKEN_SECRET is set)
# ---------------------------------------------------------------------------

def _sm_client():
    from google.cloud import secretmanager
    return secretmanager.SecretManagerServiceClient()


def _read_token_from_secret(secret_name: str) -> str | None:
    """
    Fetch the token JSON string from Secret Manager.
    Returns None if the secret has no accessible versions yet.
    """
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        raise EnvironmentError(
            "GOOGLE_CLOUD_PROJECT must be set when GOOGLE_TOKEN_SECRET is configured."
        )
    client = _sm_client()
    resource = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    try:
        response = client.access_secret_version(name=resource)
        return response.payload.data.decode("utf-8")
    except Exception:
        return None


def _write_token_to_secret(secret_name: str, token_json: str) -> None:
    """Add a new version of the token secret in Secret Manager."""
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    client = _sm_client()
    parent = f"projects/{project_id}/secrets/{secret_name}"
    client.add_secret_version(
        request={
            "parent": parent,
            "payload": {"data": token_json.encode("utf-8")},
        }
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
            creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
    elif Path(token_file).exists():
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(credentials_file).exists():
                raise FileNotFoundError(
                    f"Google OAuth credentials file not found: {credentials_file!r}\n"
                    "Download it from Google Cloud Console > APIs & Services > Credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)

        # Persist updated credentials to whichever backend is active.
        if token_secret:
            _write_token_to_secret(token_secret, creds.to_json())
        else:
            with open(token_file, "w") as f:
                f.write(creds.to_json())

    return creds


def build_gmail_service(
    credentials_file: str,
    token_file: str,
    token_secret: str | None = None,
):
    """Return an authenticated Gmail API service object."""
    creds = get_credentials(credentials_file, token_file, token_secret)
    return build("gmail", "v1", credentials=creds)


# ---------------------------------------------------------------------------
# Label helpers
# ---------------------------------------------------------------------------

def resolve_label_ids(service, label_names: list[str]) -> list[str]:
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
            created = service.users().labels().create(
                userId="me",
                body={"name": name},
            ).execute()
            ids.append(created["id"])
            name_to_id[name] = created["id"]
            print(f"[Gmail] Created label {name!r} (id: {created['id']})")

    return ids


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

def upload_message(service, raw_message: RawMessage, label_ids: list[str] | None = None) -> str:
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
    body: dict = {"raw": encoded}
    if label_ids:
        body["labelIds"] = ["INBOX", "UNREAD"] + label_ids
    result = service.users().messages().insert(
        userId="me",
        body=body,
        internalDateSource="dateHeader",
    ).execute()
    return result["id"]
