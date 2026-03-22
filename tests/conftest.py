"""Shared pytest fixtures and configuration."""

from typing import Any
from unittest.mock import Mock

import pytest

from maildrain.models import RawMessage


@pytest.fixture
def sample_email_bytes() -> bytes:
    """Sample RFC 2822 email bytes for testing."""
    return b"""From: sender@example.com
To: recipient@example.com
Subject: Test Email
Message-ID: <test123@example.com>
Date: Mon, 22 Mar 2026 10:00:00 +0000
Content-Type: text/plain; charset=utf-8

This is a test email message.
It has multiple lines.

Best regards,
Test Sender
"""


@pytest.fixture
def sample_raw_message(sample_email_bytes: bytes) -> RawMessage:
    """Sample RawMessage instance for testing."""
    return RawMessage(
        sequence=1,
        message_id="<test123@example.com>",
        raw_bytes=sample_email_bytes,
        server_name="test.imap.server.com",
        imap_uid=42,
    )


@pytest.fixture
def mock_credentials() -> Any:
    """Mock Google OAuth2 credentials."""
    mock_creds = Mock()
    mock_creds.valid = True
    mock_creds.expired = False
    mock_creds.refresh_token = "mock_refresh_token"
    mock_creds.to_json.return_value = '{"access_token": "mock_access_token"}'
    return mock_creds


@pytest.fixture
def mock_secret_manager_client() -> Any:
    """Mock Google Secret Manager client."""
    mock_client = Mock()

    # Setup default responses
    mock_response = Mock()
    mock_response.payload.data.decode.return_value = '{"token": "mock_token"}'
    mock_client.access_secret_version.return_value = mock_response

    mock_new_version = Mock()
    mock_new_version.name = "projects/test-project/secrets/test-secret/versions/2"
    mock_client.add_secret_version.return_value = mock_new_version

    mock_client.list_secret_versions.return_value = []

    return mock_client


@pytest.fixture
def mock_gmail_service() -> Any:
    """Mock Gmail API service with realistic responses."""
    service = Mock()

    # Mock labels API
    labels_api = service.users().labels()
    labels_api.list().execute.return_value = {
        "labels": [
            {"id": "INBOX", "name": "INBOX"},
            {"id": "UNREAD", "name": "UNREAD"},
            {"id": "label_work_123", "name": "Work"},
        ]
    }

    labels_api.create().execute.return_value = {
        "id": "label_new_456",
        "name": "NewLabel",
    }

    # Mock messages API
    messages_api = service.users().messages()
    messages_api.insert().execute.return_value = {
        "id": "msg_123456789",
        "threadId": "thread_123456",
    }

    return service
