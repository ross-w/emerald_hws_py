"""Tests to verify control operations send correct MQTT payloads.

These tests ensure that control commands (turn on/off, mode changes) construct
the correct MQTT message structure. This catches regressions if the payload
format is accidentally changed.
"""

import json
import pytest
from unittest.mock import Mock
from emerald_hws import EmeraldHWS
from .conftest import (
    MOCK_LOGIN_RESPONSE,
    MOCK_PROPERTY_RESPONSE_SELF,
)


@pytest.mark.parametrize(
    "method_name,method_args,expected_payload",
    [
        ("turnOn", [], {"switch": 1}),
        ("turnOff", [], {"switch": 0}),
        ("setNormalMode", [], {"mode": 1}),
        ("setBoostMode", [], {"mode": 0}),
        ("setQuietMode", [], {"mode": 2}),
    ],
)
def test_control_operations_send_correct_payload(
    mock_requests,
    mock_boto3,
    mock_mqtt5_client_builder,
    mock_auth,
    mock_io,
    mocker,
    method_name,
    method_args,
    expected_payload,
):
    """Test that control operations send correct MQTT message structure and payload."""
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

    # Get the MQTT client mock and verify publish was called
    mqtt_client = (
        mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    )
    mqtt_client.publish.assert_called_once()

    # Extract the publish packet from the call
    call_args = mqtt_client.publish.call_args
    publish_packet = call_args[0][0]  # First positional argument

    # Verify topic
    expected_topic = f"ep/heat_pump/to_gw/{hws_id}"
    assert publish_packet.topic == expected_topic, (
        f"Expected topic '{expected_topic}', got '{publish_packet.topic}'"
    )

    # Parse and verify payload structure
    payload = json.loads(publish_packet.payload)

    # Should be a list with 2 elements
    assert isinstance(payload, list), "Payload should be a list"
    assert len(payload) == 2, f"Payload should have 2 elements, got {len(payload)}"

    # First element is the header
    header = payload[0]
    assert header["device_id"] == hws_id
    assert header["namespace"] == "business"
    assert header["command"] == "control"
    assert header["direction"] == "app2gw"
    assert header["property_id"] == "prop-aaaa-1111-bbbb-2222"
    assert header["hw_id"] == "aabbccddeeff"  # From mock data
    assert "msg_id" in header

    # Second element is the control payload
    control_payload = payload[1]
    assert control_payload == expected_payload, (
        f"Expected payload {expected_payload}, got {control_payload}"
    )


def test_control_message_includes_property_details(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """Test that control messages include correct property_id and hw_id from device status."""
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
    client.turnOn(hws_id)

    # Extract the payload
    mqtt_client = (
        mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    )
    call_args = mqtt_client.publish.call_args
    publish_packet = call_args[0][0]
    payload = json.loads(publish_packet.payload)

    header = payload[0]

    # These should come from the device's full status
    assert header["property_id"] == "prop-aaaa-1111-bbbb-2222"
    assert header["hw_id"] == "aabbccddeeff"  # mac_address from mock


def test_control_message_fails_for_nonexistent_device(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """Test that control operations fail gracefully for non-existent devices."""
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

    # Attempt control on non-existent device
    with pytest.raises(Exception) as exc_info:
        client.turnOn("nonexistent-hws-id")

    assert "Unable to find HWS" in str(exc_info.value)

    # Verify no MQTT message was sent
    mqtt_client = (
        mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    )
    mqtt_client.publish.assert_not_called()


def test_control_message_topic_format(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """Test that control messages are sent to the correct MQTT topic."""
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
    client.setBoostMode(hws_id)

    # Verify topic format
    mqtt_client = (
        mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    )
    call_args = mqtt_client.publish.call_args
    publish_packet = call_args[0][0]

    # Topic should be: ep/heat_pump/to_gw/{device_id}
    assert publish_packet.topic == f"ep/heat_pump/to_gw/{hws_id}"
    assert publish_packet.topic.startswith("ep/heat_pump/to_gw/")
