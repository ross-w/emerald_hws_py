"""Tests for control operations (turn on/off, mode changes)."""
import json
import pytest
from unittest.mock import Mock, patch
from emerald_hws import EmeraldHWS
from .conftest import (
    MOCK_LOGIN_RESPONSE,
    MOCK_PROPERTY_RESPONSE_SELF,
)


def test_turn_on(mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mock_connection_event, mocker):
    """Test turning on a heat pump."""
    # Setup mocks
    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE
    mock_requests.post.return_value = mock_login

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_SELF
    mock_requests.get.return_value = mock_properties

    # Execute
    client = EmeraldHWS("test@example.com", "password")

    # Patch the connection event to avoid timeout
    mocker.patch.object(client._connection_event, "wait", return_value=True)

    client.connect()

    hws_id = "hws-1111-aaaa-2222-bbbb"
    client.turnOn(hws_id)

    # Verify MQTT publish was called
    mqtt_client = mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    mqtt_client.publish.assert_called_once()


def test_turn_off(mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mock_connection_event, mocker):
    """Test turning off a heat pump."""
    # Setup mocks
    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE
    mock_requests.post.return_value = mock_login

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_SELF
    mock_requests.get.return_value = mock_properties

    # Execute
    client = EmeraldHWS("test@example.com", "password")

    # Patch the connection event to avoid timeout
    mocker.patch.object(client._connection_event, "wait", return_value=True)

    client.connect()

    hws_id = "hws-1111-aaaa-2222-bbbb"
    client.turnOff(hws_id)

    # Verify MQTT publish was called
    mqtt_client = mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    mqtt_client.publish.assert_called_once()


def test_set_normal_mode(mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mock_connection_event, mocker):
    """Test setting heat pump to normal mode."""
    # Setup mocks
    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE
    mock_requests.post.return_value = mock_login

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_SELF
    mock_requests.get.return_value = mock_properties

    # Execute
    client = EmeraldHWS("test@example.com", "password")

    # Patch the connection event to avoid timeout
    mocker.patch.object(client._connection_event, "wait", return_value=True)

    client.connect()

    hws_id = "hws-1111-aaaa-2222-bbbb"
    client.setNormalMode(hws_id)

    # Verify MQTT publish was called
    mqtt_client = mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    mqtt_client.publish.assert_called_once()


def test_set_boost_mode(mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mock_connection_event, mocker):
    """Test setting heat pump to boost mode."""
    # Setup mocks
    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE
    mock_requests.post.return_value = mock_login

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_SELF
    mock_requests.get.return_value = mock_properties

    # Execute
    client = EmeraldHWS("test@example.com", "password")

    # Patch the connection event to avoid timeout
    mocker.patch.object(client._connection_event, "wait", return_value=True)

    client.connect()

    hws_id = "hws-1111-aaaa-2222-bbbb"
    client.setBoostMode(hws_id)

    # Verify MQTT publish was called
    mqtt_client = mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    mqtt_client.publish.assert_called_once()


def test_set_quiet_mode(mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mock_connection_event, mocker):
    """Test setting heat pump to quiet mode."""
    # Setup mocks
    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE
    mock_requests.post.return_value = mock_login

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_SELF
    mock_requests.get.return_value = mock_properties

    # Execute
    client = EmeraldHWS("test@example.com", "password")

    # Patch the connection event to avoid timeout
    mocker.patch.object(client._connection_event, "wait", return_value=True)

    client.connect()

    hws_id = "hws-1111-aaaa-2222-bbbb"
    client.setQuietMode(hws_id)

    # Verify MQTT publish was called
    mqtt_client = mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    mqtt_client.publish.assert_called_once()


