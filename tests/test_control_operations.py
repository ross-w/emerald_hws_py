"""Tests for control operations (turn on/off, mode changes).

NOTE: Detailed payload verification is now in test_control_payload_verification.py
These tests focus on basic integration - that control operations can be called
and result in MQTT publish being invoked.
"""

import json
import pytest
from unittest.mock import Mock
from emerald_hws import EmeraldHWS
from .conftest import (
    MOCK_LOGIN_RESPONSE,
    MOCK_PROPERTY_RESPONSE_SELF,
    connect_and_clear_publishes,
    mark_connected,
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
    mark_connected(client, mocker)
    connect_and_clear_publishes(client)

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
    mark_connected(client, mocker)

    assert not client._setup_complete

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # Control operation should trigger auto-connect
    client.turnOn(hws_id)

    # Verify connection was established
    assert client._setup_complete

    # Verify MQTT publish was called. The auto-connect runs first and sends its
    # own comp_query to seed state, so the control message is the last publish
    # rather than the only one - assert on both, so a control message that
    # silently stopped being sent cannot pass on the comp_query alone.
    mqtt_client = (
        mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    )
    commands = [
        json.loads(call[0][0].payload)[0]["command"]
        for call in mqtt_client.publish.call_args_list
    ]
    assert "comp_query" in commands[:-1], (
        f"auto-connect should have seeded state with a comp_query, got {commands}"
    )
    assert commands[-1] == "control", (
        f"the control message should be the final publish, got {commands}"
    )
    assert commands.count("control") == 1, (
        f"turnOn should publish exactly one control message, got {commands}"
    )
