"""Tests for control operations (turn on/off, mode changes).

NOTE: Detailed payload verification is now in test_control_payload_verification.py
These tests focus on basic integration - that control operations can be called
and result in MQTT publish being invoked.
"""

import pytest
from unittest.mock import Mock
from emerald_hws import EmeraldHWS
from .conftest import (
    MOCK_LOGIN_RESPONSE,
    MOCK_PROPERTY_RESPONSE_SELF,
)


@pytest.mark.parametrize(
    "method_name,method_args",
    [
        ("turnOn", []),
        ("turnOff", []),
        ("setNormalMode", []),
        ("setBoostMode", []),
        ("setQuietMode", []),
    ],
)
def test_control_operations_trigger_mqtt_publish(
    mock_requests,
    mock_boto3,
    mock_mqtt5_client_builder,
    mock_auth,
    mock_io,
    mocker,
    method_name,
    method_args,
):
    """Test that control operations successfully trigger MQTT publish."""
    # Setup mocks
    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE
    mock_requests.post.return_value = mock_login

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_SELF
    mock_requests.get.return_value = mock_properties

    # Create and connect client
    client = EmeraldHWS("test@example.com", "password")
    mocker.patch.object(client._connection_event, "wait", return_value=True)
    client.connect()

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # Call the control method
    method = getattr(client, method_name)
    method(hws_id, *method_args)

    # Verify MQTT publish was called
    mqtt_client = (
        mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    )
    mqtt_client.publish.assert_called_once()


def test_control_operation_auto_connects_when_disconnected(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """Test that control operations auto-connect if client is not connected."""
    # Setup mocks
    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE
    mock_requests.post.return_value = mock_login

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_SELF
    mock_requests.get.return_value = mock_properties

    # Create client but DON'T connect
    client = EmeraldHWS("test@example.com", "password")
    mocker.patch.object(client._connection_event, "wait", return_value=True)

    assert not client._is_connected

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # Control operation should trigger auto-connect
    client.turnOn(hws_id)

    # Verify connection was established
    assert client._is_connected

    # Verify MQTT publish was called
    mqtt_client = (
        mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    )
    mqtt_client.publish.assert_called_once()
