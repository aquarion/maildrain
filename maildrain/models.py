from dataclasses import dataclass, field
from enum import Enum, auto


class TransferStatus(Enum):
    SUCCESS = auto()
    GMAIL_FAILED = auto()
    ARCHIVE_FAILED = auto()


@dataclass
class RawMessage:
    """A message downloaded from a source mail server."""

    sequence: int  # 1-based position within the server's download batch
    message_id: str  # Value of the Message-ID header (used for IMAP search fallback)
    raw_bytes: bytes  # Complete RFC 2822 message bytes
    server_name: str = ""  # Name of the source server (for reporting)
    imap_uid: int | None = (
        None  # IMAP UID if downloaded via IMAP; enables direct move without search
    )


@dataclass
class TransferResult:
    """Outcome of processing one message."""

    sequence: int
    message_id: str
    status: TransferStatus
    gmail_message_id: str | None = None
    error: str | None = None


@dataclass
class Summary:
    """Aggregate results for the run."""

    total: int = 0
    succeeded: int = 0
    gmail_failed: int = 0
    archive_failed: int = 0
    results: list[TransferResult] = field(default_factory=list)
