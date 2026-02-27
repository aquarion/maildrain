import base64
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError  # noqa: F401 — re-exported for callers

from depop.models import RawMessage

# Minimal scope: insert messages only (principle of least privilege).
SCOPES = ["https://www.googleapis.com/auth/gmail.insert"]


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


def upload_message(service, raw_message: RawMessage) -> str:
    """
    Upload a single RFC 2822 message to Gmail using messages.insert.

    Uses internalDateSource='dateHeader' so Gmail respects the original
    Date: header for ordering rather than the import timestamp.

    Returns the Gmail message ID string on success.
    Raises googleapiclient.errors.HttpError on failure.
    """
    encoded = base64.urlsafe_b64encode(raw_message.raw_bytes).decode("ascii")
    result = service.users().messages().insert(
        userId="me",
        body={"raw": encoded},
        internalDateSource="dateHeader",
    ).execute()
    return result["id"]
