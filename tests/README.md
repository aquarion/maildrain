# Maildrain Tests

This directory contains comprehensive tests for the maildrain package.

## Setup

First, install the test dependencies:

```bash
poetry install --with dev
```

## Running Tests

Run all tests:
```bash
poetry run pytest
```

Run tests with coverage:
```bash
poetry run pytest --cov=maildrain --cov-report=html --cov-report=term
```

Run only unit tests:
```bash
poetry run pytest -m "unit or not (integration or slow)"
```

Run tests with verbose output:
```bash
poetry run pytest -v
```

Run specific test file:
```bash
poetry run pytest tests/test_gmail_client.py
```

Run specific test function:
```bash
poetry run pytest tests/test_gmail_client.py::TestUploadMessage::test_upload_message_basic
```

## Test Structure

- `conftest.py` - Shared pytest fixtures and configuration
- `test_models.py` - Tests for data models (RawMessage, TransferResult, etc.)
- `test_gmail_client.py` - Comprehensive tests for Gmail API interactions

## Test Coverage

### Gmail Client (`test_gmail_client.py`)

- **Secret Manager functions**: Tests for reading/writing OAuth tokens to GCP Secret Manager
- **Credentials management**: Tests for OAuth flow, token refresh, file vs. secret manager storage
- **Gmail service building**: Tests for creating authenticated Gmail API service objects
- **Label management**: Tests for resolving label names to IDs, creating new labels as needed
- **Message upload**: Tests for uploading RFC 2822 messages to Gmail with proper encoding and labeling
- **Error handling**: Tests for various API error conditions and edge cases
- **Integration tests**: End-to-end workflow tests combining multiple functions

### Models (`test_models.py`)

- **Data structures**: Tests for all dataclasses used throughout the application
- **Default values**: Verification of proper default value handling
- **Type validation**: Implicit validation through usage patterns

## Mocking Strategy

The tests use extensive mocking to avoid hitting real Google APIs:

- **Google API clients**: Mocked using `unittest.mock.Mock`
- **OAuth flow**: Mocked credential creation and refresh
- **Secret Manager**: Mocked read/write operations
- **File operations**: Mocked using `mock_open` for token file handling

## Test Markers

- `unit` - Unit tests (default, fast-running)
- `integration` - Integration tests (may be slower)
- `slow` - Explicitly slow tests

## Test Data

Test fixtures provide realistic sample data:

- Sample email messages in RFC 2822 format
- Mock credentials and API responses
- Reusable Gmail service mocks

## Contributing

When adding new features to maildrain:

1. Add corresponding tests in the appropriate test file
2. Use the existing fixtures where possible
3. Follow the established mocking patterns
4. Ensure good test coverage of both success and error paths
5. Add integration tests for complex workflows

Run tests before submitting changes:
```bash
poetry run pytest --cov=maildrain
```
