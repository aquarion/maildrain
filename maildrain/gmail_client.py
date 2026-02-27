import base64
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


def get_credentials(credentials_file: str, token_file: str) -> Credentials:
    """
    Load cached OAuth credentials from token_file if they exist and are valid.
    Refreshes silently if expired and a refresh_token is available.
    Runs the browser-based OAuth flow if no valid credentials exist,
    then persists the new token to token_file for future runs.
    """
    creds: Credentials | None = None

    if Path(token_file).exists():
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

        with open(token_file, "w") as f:
            f.write(creds.to_json())

    return creds


def build_gmail_service(credentials_file: str, token_file: str):
    """Return an authenticated Gmail API service object."""
    creds = get_credentials(credentials_file, token_file)
    return build("gmail", "v1", credentials=creds)


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
