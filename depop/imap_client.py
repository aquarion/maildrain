import email
from email import policy

from imapclient import IMAPClient
from imapclient.exceptions import IMAPClientError

from depop.models import RawMessage


def _ensure_archive_folder(client: IMAPClient, folder_name: str) -> None:
    """Create the archive folder if it does not already exist."""
    existing = [name for _flags, _delim, name in client.list_folders()]
    if folder_name not in existing:
        client.create_folder(folder_name)
        print(f"[IMAP] Created folder: {folder_name!r}")


def download_messages_imap(
    host: str,
    port: int,
    username: str,
    password: str,
) -> list[RawMessage]:
    """
    Connect to IMAP over SSL, fetch every message in INBOX, and return them
    as RawMessage objects with imap_uid set.

    The IMAP UID is stored on each message so the archive step can move it
    directly without a second Message-ID search.
    """
    messages: list[RawMessage] = []

    with IMAPClient(host, port=port, ssl=True, use_uid=True) as client:
        client.login(username, password)
        client.select_folder("INBOX", readonly=False)

        uids = client.search(["ALL"])
        print(f"[IMAP] {len(uids)} message(s) found in INBOX.")

        for sequence, uid in enumerate(uids, start=1):
            response = client.fetch([uid], ["RFC822"])
            raw_bytes = response[uid][b"RFC822"]

            parsed = email.message_from_bytes(raw_bytes, policy=policy.default)
            message_id = parsed.get("Message-ID", "").strip()

            if not message_id:
                subject = parsed.get("Subject", "(no subject)")
                print(
                    f"[IMAP] WARNING: message UID {uid} has no Message-ID "
                    f"(Subject: {subject!r}). Archive will use UID directly."
                )

            messages.append(RawMessage(
                sequence=sequence,
                message_id=message_id,
                raw_bytes=raw_bytes,
                imap_uid=uid,
            ))

    print(f"[IMAP] Downloaded {len(messages)} message(s).")
    return messages


def archive_message(
    host: str,
    port: int,
    username: str,
    password: str,
    archive_folder: str,
    message_id: str = "",
    imap_uid: int | None = None,
) -> bool:
    """
    Move a message to archive_folder.

    If imap_uid is provided (IMAP-sourced messages), moves it directly by UID —
    no search needed, and works even when Message-ID is absent.

    If imap_uid is absent (POP3-sourced messages), falls back to searching
    INBOX by the Message-ID header.

    Uses imapclient's move() which issues UID MOVE (RFC 6851) when supported,
    falling back to COPY + STORE \\Deleted + EXPUNGE otherwise.

    Returns True on success, False if the message could not be found or moved.
    """
    try:
        with IMAPClient(host, port=port, ssl=True, use_uid=True) as client:
            client.login(username, password)
            _ensure_archive_folder(client, archive_folder)
            client.select_folder("INBOX")

            if imap_uid is not None:
                uid = imap_uid
            else:
                uids = client.search(["HEADER", "Message-ID", message_id])
                if not uids:
                    print(f"[IMAP] Message not found in INBOX: {message_id!r}")
                    return False
                uid = uids[0]

            client.move([uid], archive_folder)
            return True

    except IMAPClientError as e:
        label = f"UID {imap_uid}" if imap_uid is not None else repr(message_id)
        print(f"[IMAP] Error archiving {label}: {e}")
        return False
