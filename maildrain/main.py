import logging
import sys

from googleapiclient.errors import HttpError

from maildrain.config import AppConfig, ServerConfig, load_config, load_servers
from maildrain.gmail_client import build_gmail_service, resolve_label_ids, upload_message
from maildrain.imap_client import archive_message, download_messages_imap
from maildrain.models import RawMessage, Summary, TransferResult, TransferStatus
from maildrain.pop_client import download_all_messages

logger = logging.getLogger(__name__)


def process_message(
    service, server: ServerConfig, raw_msg: RawMessage, label_ids: list[str]
) -> TransferResult:
    """
    Run a single message through the full pipeline:
      1. Upload to Gmail
      2. Archive via IMAP
    """
    # Step 1: upload to Gmail
    try:
        gmail_id = upload_message(service, raw_msg, label_ids=label_ids or None)
        logger.info(
            "Uploaded #%d (Message-ID: %r) -> Gmail ID: %s",
            raw_msg.sequence, raw_msg.message_id, gmail_id,
        )
    except HttpError as e:
        logger.error("Failed to upload #%d: %s", raw_msg.sequence, e)
        return TransferResult(
            sequence=raw_msg.sequence,
            message_id=raw_msg.message_id,
            status=TransferStatus.GMAIL_FAILED,
            error=str(e),
        )

    # Step 2: archive via IMAP.
    # IMAP-sourced messages carry a UID for direct move; POP3-sourced messages
    # fall back to Message-ID search. If neither is available, skip archive.
    if raw_msg.imap_uid is None and not raw_msg.message_id:
        return TransferResult(
            sequence=raw_msg.sequence,
            message_id=raw_msg.message_id,
            status=TransferStatus.ARCHIVE_FAILED,
            gmail_message_id=gmail_id,
            error="No Message-ID header and no IMAP UID; cannot locate message for archive.",
        )

    archived = archive_message(
        host=server.imap_host,
        port=server.imap_port,
        username=server.imap_username,
        password=server.imap_password,
        archive_folder=server.archive_folder,
        message_id=raw_msg.message_id,
        imap_uid=raw_msg.imap_uid,
    )

    if archived:
        logger.info("Archived #%d to %r", raw_msg.sequence, server.archive_folder)
        return TransferResult(
            sequence=raw_msg.sequence,
            message_id=raw_msg.message_id,
            status=TransferStatus.SUCCESS,
            gmail_message_id=gmail_id,
        )

    return TransferResult(
        sequence=raw_msg.sequence,
        message_id=raw_msg.message_id,
        status=TransferStatus.ARCHIVE_FAILED,
        gmail_message_id=gmail_id,
        error="IMAP move failed (see above for details).",
    )


def process_server(service, server: ServerConfig) -> Summary:
    """Download and transfer all messages for a single source account."""
    logger.info("Processing server: %s (%s)", server.name, server.imap_host)

    label_ids = resolve_label_ids(service, server.labels)
    if label_ids:
        logger.info("Labels to apply: %s", ", ".join(server.labels))

    try:
        if server.use_pop:
            messages = download_all_messages(
                host=server.pop_host,
                port=server.pop_port,
                username=server.pop_username,
                password=server.pop_password,
            )
        else:
            messages = download_messages_imap(
                host=server.imap_host,
                port=server.imap_port,
                username=server.imap_username,
                password=server.imap_password,
            )
    except Exception as e:
        logger.error("Fatal download error for %r: %s", server.name, e)
        return Summary()

    if not messages:
        logger.info("No messages to process.")
        return Summary()

    for msg in messages:
        msg.server_name = server.name

    summary = Summary(total=len(messages))
    for raw_msg in messages:
        result = process_message(service, server, raw_msg, label_ids)
        summary.results.append(result)
        if result.status == TransferStatus.SUCCESS:
            summary.succeeded += 1
        elif result.status == TransferStatus.GMAIL_FAILED:
            summary.gmail_failed += 1
        elif result.status == TransferStatus.ARCHIVE_FAILED:
            summary.archive_failed += 1

    return summary


def log_summary(label: str, summary: Summary) -> None:
    logger.info(
        "Summary [%s] — total: %d, succeeded: %d, gmail_failed: %d, archive_failed: %d",
        label, summary.total, summary.succeeded, summary.gmail_failed, summary.archive_failed,
    )
    failures = [r for r in summary.results if r.status != TransferStatus.SUCCESS]
    for r in failures:
        logger.error(
            "  FAILED #%d | %s | Message-ID: %r | %s",
            r.sequence, r.status.name, r.message_id, r.error,
        )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # 1. Load application config (Gmail auth + servers file path)
    config = load_config()

    # 2. Load server list from TOML
    try:
        servers = load_servers(config.servers_file)
    except (FileNotFoundError, ValueError) as e:
        logger.error("Configuration error: %s", e)
        sys.exit(1)

    # 3. Authenticate with Gmail (opens browser on first run)
    logger.info("Authenticating with Gmail...")
    try:
        service = build_gmail_service(
            config.google_credentials_file,
            config.google_token_file,
            config.google_token_secret,
        )
    except FileNotFoundError as e:
        logger.error("Auth error: %s", e)
        sys.exit(1)

    # 4. Process each server
    summaries: list[tuple[str, Summary]] = []
    for server in servers:
        summary = process_server(service, server)
        summaries.append((server.name, summary))

    # 5. Log summaries
    grand = Summary()
    for name, s in summaries:
        log_summary(name, s)
        grand.total += s.total
        grand.succeeded += s.succeeded
        grand.gmail_failed += s.gmail_failed
        grand.archive_failed += s.archive_failed
        grand.results.extend(s.results)

    if len(servers) > 1:
        log_summary("TOTAL", grand)

    if grand.gmail_failed or grand.archive_failed:
        sys.exit(2)
