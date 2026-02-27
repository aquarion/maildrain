import sys

from googleapiclient.errors import HttpError

from maildrain.config import AppConfig, ServerConfig, load_config, load_servers
from maildrain.gmail_client import build_gmail_service, resolve_label_ids, upload_message
from maildrain.imap_client import archive_message, download_messages_imap
from maildrain.models import RawMessage, Summary, TransferResult, TransferStatus
from maildrain.pop_client import download_all_messages


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
        print(
            f"[Gmail] Uploaded #{raw_msg.sequence} "
            f"(Message-ID: {raw_msg.message_id!r}) -> Gmail ID: {gmail_id}"
        )
    except HttpError as e:
        print(f"[Gmail] FAILED to upload #{raw_msg.sequence}: {e}")
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
        print(f"[IMAP] Archived #{raw_msg.sequence} to {server.archive_folder!r}")
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
    print(f"\n{'=' * 60}")
    print(f"[Server] {server.name}  ({server.imap_host})")
    print(f"{'=' * 60}")

    label_ids = resolve_label_ids(service, server.labels)
    if label_ids:
        print(f"[Gmail] Labels to apply: {', '.join(server.labels)}")

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
        print(f"[Download] Fatal error for {server.name!r}: {e}", file=sys.stderr)
        return Summary()

    if not messages:
        print("No messages to process.")
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


def print_summary(label: str, summary: Summary) -> None:
    print(f"\n--- {label} ---")
    print(f"  Total    : {summary.total}")
    print(f"  Succeeded: {summary.succeeded}")
    print(f"  Gmail failed  : {summary.gmail_failed}")
    print(f"  Archive failed: {summary.archive_failed}")

    failures = [r for r in summary.results if r.status != TransferStatus.SUCCESS]
    if failures:
        print("  Failures:")
        for r in failures:
            print(
                f"    #{r.sequence} | {r.status.name} | "
                f"Message-ID: {r.message_id!r} | {r.error}"
            )


def main() -> None:
    # 1. Load application config (Gmail auth + servers file path)
    config = load_config()

    # 2. Load server list from TOML
    try:
        servers = load_servers(config.servers_file)
    except (FileNotFoundError, ValueError) as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    # 3. Authenticate with Gmail (opens browser on first run)
    print("[Auth] Authenticating with Gmail...")
    try:
        service = build_gmail_service(
            config.google_credentials_file,
            config.google_token_file,
            config.google_token_secret,
        )
    except FileNotFoundError as e:
        print(f"Auth error: {e}", file=sys.stderr)
        sys.exit(1)

    # 4. Process each server
    summaries: list[tuple[str, Summary]] = []
    for server in servers:
        summary = process_server(service, server)
        summaries.append((server.name, summary))

    # 5. Print summaries
    print(f"\n{'=' * 60}")
    print("DEPOP SUMMARY")
    print(f"{'=' * 60}")

    grand = Summary()
    for name, s in summaries:
        print_summary(name, s)
        grand.total += s.total
        grand.succeeded += s.succeeded
        grand.gmail_failed += s.gmail_failed
        grand.archive_failed += s.archive_failed
        grand.results.extend(s.results)

    if len(servers) > 1:
        print_summary("TOTAL", grand)

    print(f"{'=' * 60}")

    if grand.gmail_failed or grand.archive_failed:
        sys.exit(2)
