"""Tests for property handling functionality."""

import pytest
from unittest.mock import Mock
from emerald_hws import EmeraldHWS
from .conftest import (
    MOCK_LOGIN_RESPONSE,
    MOCK_PROPERTY_RESPONSE_SELF,
    MOCK_PROPERTY_RESPONSE_SHARED,
    MOCK_PROPERTY_RESPONSE_MIXED,
    MOCK_PROPERTY_RESPONSE_EMPTY,
)


def test_get_properties_from_self_property(mock_requests):
    """Test retrieving properties from 'property' array."""
    # Setup mocks
    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_SELF

    mock_requests.post.return_value = mock_login
    mock_requests.get.return_value = mock_properties

    # Execute
    client = EmeraldHWS("test@example.com", "password")
    client.getAllHWS()

    # Assertions
    assert len(client.properties) == 1
    assert client.properties[0]["id"] == "prop-aaaa-1111-bbbb-2222"
    assert client.properties[0]["property_type"] == "Self"
    assert len(client.properties[0]["heat_pump"]) == 1
    assert client.properties[0]["heat_pump"][0]["id"] == "hws-1111-aaaa-2222-bbbb"


def test_get_properties_from_shared_property(mock_requests):
    """Test retrieving properties from 'shared_property' array."""
    # Setup mocks
    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_SHARED

    mock_requests.post.return_value = mock_login
    mock_requests.get.return_value = mock_properties

    # Execute
    client = EmeraldHWS("test@example.com", "password")
    client.getAllHWS()

    # Assertions
    assert len(client.properties) == 1
    assert client.properties[0]["id"] == "prop-9999-eeee-8888-ffff"
    assert client.properties[0]["property_type"] == "Shared"
    assert len(client.properties[0]["heat_pump"]) == 1
    assert client.properties[0]["heat_pump"][0]["id"] == "hws-9999-eeee-8888-ffff"


def test_get_properties_mixed(mock_requests):
    """Test retrieving properties when both arrays are populated."""
    # Setup mocks
    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_MIXED

    mock_requests.post.return_value = mock_login
    mock_requests.get.return_value = mock_properties

    # Execute
    client = EmeraldHWS("test@example.com", "password")
    client.getAllHWS()

    # Assertions - should have both properties
    assert len(client.properties) == 2

    # Check we have one of each type
    property_types = [prop["property_type"] for prop in client.properties]
    assert "Self" in property_types
    assert "Shared" in property_types

    # Verify all heat pumps are accessible
    all_hws_ids = [hws["id"] for prop in client.properties for hws in prop["heat_pump"]]

    assert "hws-1111-aaaa-2222-bbbb" in all_hws_ids
    assert "hws-9999-eeee-8888-ffff" in all_hws_ids


def test_empty_properties_raises_exception(mock_requests):
    """Test that empty property list raises an exception."""
    # Setup mocks
    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_EMPTY

    mock_requests.post.return_value = mock_login
    mock_requests.get.return_value = mock_properties

    # Execute and verify exception
    client = EmeraldHWS("test@example.com", "password")

    with pytest.raises(Exception) as exc_info:
        client.getAllHWS()

    assert "No heat pumps found" in str(exc_info.value)


def test_auto_login_if_no_token(mock_requests):
    """Test that getAllHWS automatically logs in if no token exists."""
    # Setup mocks
    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_SELF

    mock_requests.post.return_value = mock_login
    mock_requests.get.return_value = mock_properties

    # Execute - don't call getLoginToken() manually
    client = EmeraldHWS("test@example.com", "password")
    assert client.token == ""  # No token yet

    client.getAllHWS()

    # Should have logged in automatically
    assert client.token == "mock_jwt_token_12345"
    assert mock_requests.post.called  # Login was called
