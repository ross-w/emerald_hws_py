"""Tests for reconnection behaviour and state persistence."""

import copy
from unittest.mock import Mock
from emerald_hws import EmeraldHWS
from .conftest import (
    MOCK_LOGIN_RESPONSE,
    MOCK_PROPERTY_RESPONSE_SELF,
)


def test_auto_connection_on_operation_when_disconnected(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """Test that operations auto-connect when client is disconnected."""
    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE
    mock_requests.post.return_value = mock_login

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_SELF
    mock_requests.get.return_value = mock_properties

    # Create client but don't connect
    client = EmeraldHWS("test@example.com", "password")
    mocker.patch.object(client._connection_event, "wait", return_value=True)

    assert not client._is_connected

    # Attempt operation - should auto-connect
    hws_id = "hws-1111-aaaa-2222-bbbb"
    client.turnOn(hws_id)

    # Verify auto-connection occurred
    assert client._is_connected
    assert mock_boto3.client.called
    assert mock_mqtt5_client_builder.websockets_with_default_aws_signing.called


def test_state_preservation_during_reconnection(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """Test that manually set state is preserved during reconnection."""
    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE
    mock_requests.post.return_value = mock_login

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_SELF
    mock_requests.get.return_value = mock_properties

    # Execute
    client = EmeraldHWS("test@example.com", "password")
    mocker.patch.object(client._connection_event, "wait", return_value=True)
    client.connect()

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # Manually set some state (simulating previous MQTT updates)
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client.properties[0]["heat_pump"][0]["last_state"]["temp_current"] = 65
    client.properties[0]["heat_pump"][0]["last_state"]["switch"] = 1
    client.properties[0]["heat_pump"][0]["last_state"]["mode"] = 2

    # Verify state is set
    assert client.properties[0]["heat_pump"][0]["last_state"]["temp_current"] == 65
    assert client.isOn(hws_id) is True
    assert client.currentMode(hws_id) == 2

    # Reconnect
    client.reconnectMQTT()

    # Verify state is preserved
    assert client.properties[0]["heat_pump"][0]["last_state"]["temp_current"] == 65
    assert client.isOn(hws_id) is True
    assert client.currentMode(hws_id) == 2


def test_mqtt_subscriptions_after_reconnection(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """Test that MQTT subscriptions are re-established after reconnection."""
    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE
    mock_requests.post.return_value = mock_login

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_SELF
    mock_requests.get.return_value = mock_properties

    # Execute
    client = EmeraldHWS("test@example.com", "password")
    mocker.patch.object(client._connection_event, "wait", return_value=True)
    client.connect()

    # Track subscription calls
    subscribe_calls = []
    original_subscribe = mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value.subscribe

    def track_subscribe(*args, **kwargs):
        subscribe_calls.append(True)
        return original_subscribe(*args, **kwargs)

    mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value.subscribe = track_subscribe

    # Initial connection should subscribe
    initial_subscribe_count = len(subscribe_calls)

    # Reconnect - should subscribe again
    client.reconnectMQTT()

    # Verify subscription was called again
    assert len(subscribe_calls) > initial_subscribe_count
