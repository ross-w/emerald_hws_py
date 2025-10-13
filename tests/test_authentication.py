"""Tests for authentication functionality."""

import pytest
from unittest.mock import Mock
from emerald_hws import EmeraldHWS
from .conftest import MOCK_LOGIN_RESPONSE, MOCK_LOGIN_FAILURE_RESPONSE


def test_successful_login(mock_requests):
    """Test successful login with valid credentials."""
    # Setup mock
    mock_response = Mock()
    mock_response.json.return_value = MOCK_LOGIN_RESPONSE
    mock_requests.post.return_value = mock_response

    # Create client and login
    client = EmeraldHWS("test@example.com", "password123")
    result = client.getLoginToken()

    # Assertions
    assert result is True
    assert client.token == "mock_jwt_token_12345"
    mock_requests.post.assert_called_once()

    # Verify the API endpoint was called correctly
    call_args = mock_requests.post.call_args
    assert "api.emerald-ems.com.au" in call_args[0][0]
    assert "sign-in" in call_args[0][0]


def test_failed_login(mock_requests):
    """Test failed login with invalid credentials."""
    # Setup mock
    mock_response = Mock()
    mock_response.json.return_value = MOCK_LOGIN_FAILURE_RESPONSE
    mock_requests.post.return_value = mock_response

    # Create client and attempt login
    client = EmeraldHWS("test@example.com", "wrongpassword")

    # Should raise exception on failed login
    with pytest.raises(Exception) as exc_info:
        client.getLoginToken()

    assert "Failed to log into Emerald API" in str(exc_info.value)
    assert client.token == ""
