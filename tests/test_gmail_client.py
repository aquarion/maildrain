import base64
import os
from typing import Any
from unittest.mock import Mock, mock_open, patch

import pytest
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

from maildrain.gmail_client import (
    _read_token_from_secret,
    _write_token_to_secret,
    build_gmail_service,
    get_credentials,
    resolve_label_ids,
    upload_message,
)
from maildrain.models import RawMessage


class TestSecretManager:
    """Tests for Secret Manager helper functions."""

    @patch("maildrain.gmail_client._sm_client")
    def test_read_token_from_secret_success(self, mock_sm_client: Any) -> None:
        """Test successfully reading token from Secret Manager."""
        # Setup
        mock_client = Mock()
        mock_sm_client.return_value = mock_client
        mock_response = Mock()
        mock_response.payload.data.decode.return_value = '{"token": "test_token"}'
        mock_client.access_secret_version.return_value = mock_response

        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "test-project"}):
            result = _read_token_from_secret("test-secret")

        assert result == '{"token": "test_token"}'
        mock_client.access_secret_version.assert_called_once_with(
            name="projects/test-project/secrets/test-secret/versions/latest"
        )

    @patch("maildrain.gmail_client._sm_client")
    def test_read_token_from_secret_not_found(self, mock_sm_client: Any) -> None:
        """Test reading token when secret doesn't exist."""
        mock_client = Mock()
        mock_sm_client.return_value = mock_client
        mock_client.access_secret_version.side_effect = Exception("Not found")

        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "test-project"}):
            result = _read_token_from_secret("test-secret")

        assert result is None

    def test_read_token_from_secret_no_project(self) -> None:
        """Test reading token fails when GOOGLE_CLOUD_PROJECT is not set."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(OSError, match="GOOGLE_CLOUD_PROJECT must be set"):
                _read_token_from_secret("test-secret")

    @patch("maildrain.gmail_client._sm_client")
    def test_write_token_to_secret(self, mock_sm_client: Any) -> None:
        """Test writing token to Secret Manager."""
        mock_client = Mock()
        mock_sm_client.return_value = mock_client

        # Mock the new version creation
        mock_new_version = Mock()
        mock_new_version.name = "projects/test-project/secrets/test-secret/versions/2"
        mock_client.add_secret_version.return_value = mock_new_version

        # Mock listing existing versions
        mock_old_version = Mock()
        mock_old_version.name = "projects/test-project/secrets/test-secret/versions/1"
        mock_client.list_secret_versions.return_value = [mock_old_version]

        token_json = '{"token": "updated_token"}'

        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "test-project"}):
            _write_token_to_secret("test-secret", token_json)

        # Verify new version was created
        mock_client.add_secret_version.assert_called_once_with(
            request={
                "parent": "projects/test-project/secrets/test-secret",
                "payload": {"data": token_json.encode("utf-8")},
            }
        )

        # Verify old version was disabled
        mock_client.disable_secret_version.assert_called_once_with(
            request={"name": mock_old_version.name}
        )


class TestGetCredentials:
    """Tests for the get_credentials function."""

    @patch("maildrain.gmail_client._read_token_from_secret")
    @patch("google.oauth2.credentials.Credentials.from_authorized_user_info")
    def test_get_credentials_from_secret_manager(
        self, mock_from_user_info: Any, mock_read_token: Any
    ) -> None:
        """Test getting credentials from Secret Manager."""
        token_json = '{"token": "test_token"}'
        mock_read_token.return_value = token_json

        mock_creds = Mock(spec=Credentials)
        mock_creds.valid = True
        mock_from_user_info.return_value = mock_creds

        result = get_credentials("creds.json", "token.json", "test-secret")

        assert result == mock_creds
        mock_read_token.assert_called_once_with("test-secret")
        mock_from_user_info.assert_called_once()

    @patch("pathlib.Path.exists")
    @patch("google.oauth2.credentials.Credentials.from_authorized_user_file")
    def test_get_credentials_from_file(
        self, mock_from_file: Any, mock_exists: Any
    ) -> None:
        """Test getting credentials from file."""
        mock_exists.return_value = True

        mock_creds = Mock(spec=Credentials)
        mock_creds.valid = True
        mock_from_file.return_value = mock_creds

        result = get_credentials("creds.json", "token.json")

        assert result == mock_creds
        mock_from_file.assert_called_once()

    @patch("pathlib.Path.exists")
    @patch("google.oauth2.credentials.Credentials.from_authorized_user_file")
    @patch("google.auth.transport.requests.Request")
    @patch("builtins.open", new_callable=mock_open)
    def test_get_credentials_refresh_token(
        self, mock_file: Any, mock_request: Any, mock_from_file: Any, mock_exists: Any
    ) -> None:
        """Test refreshing expired credentials."""
        mock_exists.return_value = True

        mock_creds = Mock(spec=Credentials)
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "old_refresh_token"
        mock_from_file.return_value = mock_creds

        # After refresh, credentials should be valid
        def refresh_side_effect(request: Any) -> None:
            mock_creds.valid = True
            mock_creds.refresh_token = "new_refresh_token"  # Token changed

        mock_creds.refresh.side_effect = refresh_side_effect
        mock_creds.to_json.return_value = '{"token": "refreshed"}'

        result = get_credentials("creds.json", "token.json")

        assert result == mock_creds
        assert result.valid
        mock_creds.refresh.assert_called_once()
        mock_file.assert_called_with("token.json", "w")

    @patch("maildrain.gmail_client.Path")
    @patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file")
    @patch("builtins.open", new_callable=mock_open)
    def test_get_credentials_oauth_flow(
        self, mock_file: Any, mock_flow_class: Any, mock_path: Any
    ) -> None:
        """Test OAuth flow for new credentials."""

        # Mock Path to return different results for exists() calls
        def path_side_effect(filename: str) -> Any:
            mock_path_instance = Mock()
            if filename == "creds.json":
                mock_path_instance.exists.return_value = True
            else:  # token.json
                mock_path_instance.exists.return_value = False
            return mock_path_instance

        mock_path.side_effect = path_side_effect

        mock_flow = Mock()
        mock_flow_class.return_value = mock_flow

        mock_creds = Mock(spec=Credentials)
        mock_creds.valid = True
        mock_creds.to_json.return_value = '{"token": "new_token"}'
        mock_flow.run_local_server.return_value = mock_creds

        result = get_credentials("creds.json", "token.json")

        assert result == mock_creds
        mock_flow.run_local_server.assert_called_once_with(port=0)
        mock_file.assert_called_with("token.json", "w")

    @patch("pathlib.Path.exists")
    def test_get_credentials_missing_credentials_file(self, mock_exists: Any) -> None:
        """Test error when credentials file is missing."""
        mock_exists.return_value = False  # Both files don't exist

        with pytest.raises(
            FileNotFoundError, match="Google OAuth credentials file not found"
        ):
            get_credentials("missing_creds.json", "token.json")


class TestBuildGmailService:
    """Tests for the build_gmail_service function."""

    @patch("maildrain.gmail_client.get_credentials")
    @patch("maildrain.gmail_client.build")
    def test_build_gmail_service(self, mock_build: Any, mock_get_creds: Any) -> None:
        """Test building Gmail service."""
        mock_creds = Mock(spec=Credentials)
        mock_get_creds.return_value = mock_creds

        mock_service = Mock()
        mock_build.return_value = mock_service

        result = build_gmail_service("creds.json", "token.json", "secret")

        assert result == mock_service
        mock_get_creds.assert_called_once_with("creds.json", "token.json", "secret")
        mock_build.assert_called_once_with("gmail", "v1", credentials=mock_creds)


class TestResolveLabelIds:
    """Tests for the resolve_label_ids function."""

    def test_resolve_label_ids_empty_list(self) -> None:
        """Test with empty label names list."""
        mock_service = Mock()

        result = resolve_label_ids(mock_service, [])

        assert result == []
        mock_service.users.assert_not_called()

    def test_resolve_label_ids_existing_labels(self) -> None:
        """Test with existing labels."""
        mock_service = Mock()
        mock_service.users().labels().list().execute.return_value = {
            "labels": [
                {"name": "Work", "id": "label_work_123"},
                {"name": "Personal", "id": "label_personal_456"},
            ]
        }

        result = resolve_label_ids(mock_service, ["Work", "Personal"])

        assert result == ["label_work_123", "label_personal_456"]

    def test_resolve_label_ids_create_new_labels(self) -> None:
        """Test creating new labels."""
        mock_service = Mock()
        mock_service.users().labels().list().execute.return_value = {
            "labels": [
                {"name": "Existing", "id": "label_existing_123"},
            ]
        }
        mock_service.users().labels().create().execute.return_value = {
            "id": "label_new_456",
            "name": "NewLabel",
        }

        result = resolve_label_ids(mock_service, ["Existing", "NewLabel"])

        assert result == ["label_existing_123", "label_new_456"]
        create_call = mock_service.users().labels().create
        create_call.assert_called_with(userId="me", body={"name": "NewLabel"})

    def test_resolve_label_ids_mixed(self) -> None:
        """Test with mix of existing and new labels."""
        mock_service = Mock()
        mock_service.users().labels().list().execute.return_value = {
            "labels": [{"name": "Work", "id": "label_work_123"}]
        }

        # Mock multiple create calls for new labels
        create_mock = mock_service.users().labels().create()
        create_mock.execute.side_effect = [
            {"id": "label_personal_456", "name": "Personal"},
            {"id": "label_urgent_789", "name": "Urgent"},
        ]

        result = resolve_label_ids(mock_service, ["Work", "Personal", "Urgent"])

        assert result == ["label_work_123", "label_personal_456", "label_urgent_789"]
        assert create_mock.execute.call_count == 2


class TestUploadMessage:
    """Tests for the upload_message function."""

    def test_upload_message_basic(self) -> None:
        """Test basic message upload without labels."""
        mock_service = Mock()
        mock_service.users().messages().insert().execute.return_value = {
            "id": "msg_123456"
        }

        raw_message = RawMessage(
            sequence=1,
            message_id="<test@example.com>",
            raw_bytes=b"From: test@example.com\nTo: dest@example.com\n\nTest message",
        )

        result = upload_message(mock_service, raw_message)

        assert result == "msg_123456"

        # Verify the API call - check that insert was called with correct params
        expected_encoded = base64.urlsafe_b64encode(raw_message.raw_bytes).decode(
            "ascii"
        )
        insert_call = mock_service.users().messages().insert
        insert_call.assert_called_with(
            userId="me", body={"raw": expected_encoded}, internalDateSource="dateHeader"
        )

    def test_upload_message_with_labels(self) -> None:
        """Test uploading message with labels."""
        mock_service = Mock()
        mock_service.users().messages().insert().execute.return_value = {
            "id": "msg_789012"
        }

        raw_message = RawMessage(
            sequence=2,
            message_id="<test2@example.com>",
            raw_bytes=b"From: test2@example.com\nTo: dest@example.com\n\nTest message 2",
        )

        label_ids = ["label_work_123", "label_urgent_456"]

        result = upload_message(mock_service, raw_message, label_ids)

        assert result == "msg_789012"

        # Verify the API call includes labels
        expected_encoded = base64.urlsafe_b64encode(raw_message.raw_bytes).decode(
            "ascii"
        )
        insert_call = mock_service.users().messages().insert
        insert_call.assert_called_with(
            userId="me",
            body={
                "raw": expected_encoded,
                "labelIds": ["INBOX", "UNREAD", "label_work_123", "label_urgent_456"],
            },
            internalDateSource="dateHeader",
        )

    def test_upload_message_api_error(self) -> None:
        """Test handling API errors during upload."""
        mock_service = Mock()
        mock_service.users().messages().insert().execute.side_effect = HttpError(
            resp=Mock(status=400), content=b'{"error": "Invalid message"}'
        )

        raw_message = RawMessage(
            sequence=3,
            message_id="<invalid@example.com>",
            raw_bytes=b"Invalid message format",
        )

        with pytest.raises(HttpError):
            upload_message(mock_service, raw_message)


# Test fixtures and utilities
@pytest.fixture
def sample_raw_message() -> RawMessage:
    """Create a sample RawMessage for testing."""
    return RawMessage(
        sequence=1,
        message_id="<test@example.com>",
        raw_bytes=b"From: test@example.com\nTo: dest@example.com\nSubject: Test\n\nHello World",
        server_name="test.server.com",
    )


@pytest.fixture
def mock_gmail_service() -> Any:
    """Create a mock Gmail service for testing."""
    service = Mock()

    # Setup default responses
    service.users().labels().list().execute.return_value = {"labels": []}
    service.users().messages().insert().execute.return_value = {"id": "mock_msg_id"}
    service.users().labels().create().execute.return_value = {
        "id": "mock_label_id",
        "name": "MockLabel",
    }

    return service


class TestIntegration:
    """Integration-style tests that combine multiple functions."""

    def test_full_upload_workflow(
        self, mock_gmail_service: Any, sample_raw_message: RawMessage
    ) -> None:
        """Test the full workflow of resolving labels and uploading a message."""
        # Setup existing labels
        mock_gmail_service.users().labels().list().execute.return_value = {
            "labels": [{"name": "Work", "id": "label_work_123"}]
        }

        # Setup new label creation
        mock_gmail_service.users().labels().create().execute.return_value = {
            "id": "label_important_456",
            "name": "Important",
        }

        # Setup message upload
        mock_gmail_service.users().messages().insert().execute.return_value = {
            "id": "uploaded_msg_789"
        }

        # Resolve labels (one existing, one new)
        label_ids = resolve_label_ids(mock_gmail_service, ["Work", "Important"])
        assert label_ids == ["label_work_123", "label_important_456"]

        # Upload message with resolved labels
        message_id = upload_message(mock_gmail_service, sample_raw_message, label_ids)
        assert message_id == "uploaded_msg_789"
