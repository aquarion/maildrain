import email
import poplib
from email import policy

from depop.models import RawMessage


def download_all_messages(
    host: str,
    port: int,
    username: str,
    password: str,
) -> list[RawMessage]:
    """
    Connect to POP3 over SSL, retrieve every message in the inbox,
    and return them as RawMessage objects.

    Does NOT delete messages from the POP server. Deletion/archiving
    happens via IMAP after a successful Gmail upload.

    poplib.retr() returns (response, ['line1', 'line2', ...], octets).
    Each line is a bytes object. Joining with b'\\r\\n' reconstructs the
    RFC 2822 message (poplib handles leading-dot unescaping internally).
    """
    messages: list[RawMessage] = []

    conn = poplib.POP3_SSL(host, port)
    try:
        conn.user(username)
        conn.pass_(password)

        count, _size = conn.stat()
        print(f"[POP3] {count} message(s) found on server.")

        for msg_num in range(1, count + 1):
            _response, lines, _octets = conn.retr(msg_num)
            raw_bytes = b"\r\n".join(lines)

            parsed = email.message_from_bytes(raw_bytes, policy=policy.default)
            message_id = parsed.get("Message-ID", "").strip()

            if not message_id:
                subject = parsed.get("Subject", "(no subject)")
                print(
                    f"[POP3] WARNING: message #{msg_num} has no Message-ID "
                    f"(Subject: {subject!r}). IMAP archive will be skipped."
                )

            messages.append(RawMessage(
                sequence=msg_num,
                message_id=message_id,
                raw_bytes=raw_bytes,
            ))

        print(f"[POP3] Downloaded {len(messages)} message(s).")
    finally:
        conn.quit()

    return messages
