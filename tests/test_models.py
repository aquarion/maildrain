"""Tests for the maildrain.models module."""

from maildrain.models import RawMessage, Summary, TransferResult, TransferStatus


class TestRawMessage:
    """Tests for the RawMessage dataclass."""

    def test_raw_message_creation(self) -> None:
        """Test creating a RawMessage instance."""
        message = RawMessage(
            sequence=1,
            message_id="<test@example.com>",
            raw_bytes=b"test message bytes",
            server_name="test.server.com",
            imap_uid=42,
        )

        assert message.sequence == 1
        assert message.message_id == "<test@example.com>"
        assert message.raw_bytes == b"test message bytes"
        assert message.server_name == "test.server.com"
        assert message.imap_uid == 42

    def test_raw_message_defaults(self) -> None:
        """Test RawMessage with default values."""
        message = RawMessage(
            sequence=5, message_id="<minimal@example.com>", raw_bytes=b"minimal message"
        )

        assert message.sequence == 5
        assert message.message_id == "<minimal@example.com>"
        assert message.raw_bytes == b"minimal message"
        assert message.server_name == ""  # default
        assert message.imap_uid is None  # default


class TestTransferResult:
    """Tests for the TransferResult dataclass."""

    def test_transfer_result_success(self) -> None:
        """Test TransferResult for successful transfer."""
        result = TransferResult(
            sequence=1,
            message_id="<success@example.com>",
            status=TransferStatus.SUCCESS,
            gmail_message_id="gmail_msg_123",
            error=None,
        )

        assert result.sequence == 1
        assert result.message_id == "<success@example.com>"
        assert result.status == TransferStatus.SUCCESS
        assert result.gmail_message_id == "gmail_msg_123"
        assert result.error is None

    def test_transfer_result_failure(self) -> None:
        """Test TransferResult for failed transfer."""
        result = TransferResult(
            sequence=2,
            message_id="<failed@example.com>",
            status=TransferStatus.GMAIL_FAILED,
            error="API rate limit exceeded",
        )

        assert result.sequence == 2
        assert result.message_id == "<failed@example.com>"
        assert result.status == TransferStatus.GMAIL_FAILED
        assert result.gmail_message_id is None  # default
        assert result.error == "API rate limit exceeded"

    def test_transfer_result_defaults(self) -> None:
        """Test TransferResult with default values."""
        result = TransferResult(
            sequence=3,
            message_id="<minimal@example.com>",
            status=TransferStatus.ARCHIVE_FAILED,
        )

        assert result.gmail_message_id is None
        assert result.error is None


class TestTransferStatus:
    """Tests for the TransferStatus enum."""

    def test_transfer_status_values(self) -> None:
        """Test all TransferStatus enum values."""
        assert TransferStatus.SUCCESS.name == "SUCCESS"
        assert TransferStatus.GMAIL_FAILED.name == "GMAIL_FAILED"
        assert TransferStatus.ARCHIVE_FAILED.name == "ARCHIVE_FAILED"

        # Ensure they're all distinct
        assert len(set(TransferStatus)) == 3


class TestSummary:
    """Tests for the Summary dataclass."""

    def test_summary_creation(self) -> None:
        """Test creating a Summary instance."""
        results = [
            TransferResult(1, "<msg1@example.com>", TransferStatus.SUCCESS),
            TransferResult(2, "<msg2@example.com>", TransferStatus.GMAIL_FAILED),
        ]

        summary = Summary(
            total=10, succeeded=8, gmail_failed=1, archive_failed=1, results=results
        )

        assert summary.total == 10
        assert summary.succeeded == 8
        assert summary.gmail_failed == 1
        assert summary.archive_failed == 1
        assert len(summary.results) == 2
        assert summary.results[0].status == TransferStatus.SUCCESS

    def test_summary_defaults(self) -> None:
        """Test Summary with default values."""
        summary = Summary()

        assert summary.total == 0
        assert summary.succeeded == 0
        assert summary.gmail_failed == 0
        assert summary.archive_failed == 0
        assert summary.results == []

    def test_summary_calculations(self) -> None:
        """Test that summary counts make sense."""
        summary = Summary(total=5, succeeded=3, gmail_failed=1, archive_failed=1)

        # Total should equal sum of outcomes
        assert (
            summary.total
            == summary.succeeded + summary.gmail_failed + summary.archive_failed
        )

    def test_summary_with_results(self) -> None:
        """Test Summary populated with actual results."""
        results = [
            TransferResult(
                1, "<msg1@example.com>", TransferStatus.SUCCESS, "gmail_123"
            ),
            TransferResult(
                2, "<msg2@example.com>", TransferStatus.SUCCESS, "gmail_456"
            ),
            TransferResult(
                3,
                "<msg3@example.com>",
                TransferStatus.GMAIL_FAILED,
                error="Network error",
            ),
            TransferResult(
                4,
                "<msg4@example.com>",
                TransferStatus.ARCHIVE_FAILED,
                "gmail_789",
                "Timeout",
            ),
        ]

        summary = Summary(
            total=4, succeeded=2, gmail_failed=1, archive_failed=1, results=results
        )

        # Verify the results match the counts
        success_count = len([r for r in results if r.status == TransferStatus.SUCCESS])
        gmail_failed_count = len(
            [r for r in results if r.status == TransferStatus.GMAIL_FAILED]
        )
        archive_failed_count = len(
            [r for r in results if r.status == TransferStatus.ARCHIVE_FAILED]
        )

        assert success_count == summary.succeeded
        assert gmail_failed_count == summary.gmail_failed
        assert archive_failed_count == summary.archive_failed
        assert len(results) == summary.total
