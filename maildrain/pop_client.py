import email
import logging
import poplib
from email import policy

from maildrain.models import RawMessage

logger = logging.getLogger(__name__)


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
        logger.info("%d message(s) found on server.", count)

        for msg_num in range(1, count + 1):
            _response, lines, _octets = conn.retr(msg_num)
            raw_bytes = b"\r\n".join(lines)

            parsed = email.message_from_bytes(raw_bytes, policy=policy.default)
            message_id = parsed.get("Message-ID", "").strip()

            if not message_id:
                subject = parsed.get("Subject", "(no subject)")
                logger.warning(
                    "Message #%d has no Message-ID (Subject: %r). "
                    "IMAP archive will be skipped.",
                    msg_num, subject,
                )

            messages.append(RawMessage(
                sequence=msg_num,
                message_id=message_id,
                raw_bytes=raw_bytes,
            ))

        logger.info("Downloaded %d message(s).", len(messages))
    finally:
        conn.quit()

    return messages
