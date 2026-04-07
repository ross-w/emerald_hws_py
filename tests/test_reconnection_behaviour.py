"""Tests for reconnection behaviour and state persistence."""

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


def test_status_requested_via_mqtt_during_reconnection(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """Test that comp_query is sent via MQTT during reconnection to refresh state.

    When reconnecting, requestAllStatusUpdates() sends comp_query MQTT messages
    to each HWS to trigger them to report their current status. This is what
    the official Emerald app does and avoids replacing MQTT state with stale API data.
    """
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

    mqtt_client = (
        mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    )

    # Record publish call count after initial connect
    publish_count_after_connect = mqtt_client.publish.call_count

    # Reconnect — should send comp_query via MQTT publish
    client.reconnectMQTT()

    # Verify MQTT publish was called during reconnect (for comp_query)
    assert mqtt_client.publish.call_count > publish_count_after_connect


def test_status_request_failure_during_reconnection_is_non_fatal(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """Test that a failed MQTT status request during reconnect doesn't break the connection."""
    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE
    mock_requests.post.return_value = mock_login

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_SELF
    mock_requests.get.return_value = mock_properties

    client = EmeraldHWS("test@example.com", "password")
    mocker.patch.object(client._connection_event, "wait", return_value=True)
    client.connect()

    # Make MQTT publish fail on reconnect (simulating MQTT issues)
    mqtt_client = (
        mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    )
    mqtt_client.publish.return_value.result.side_effect = Exception(
        "MQTT publish failed"
    )

    # Reconnect should not raise even if status request fails
    client.reconnectMQTT()

    # MQTT client should still be set up and connection healthy
    assert client.mqttClient is not None
    assert client._is_connected is True


def test_status_request_exception_during_reconnection_is_non_fatal(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """Test that reconnect survives when requestAllStatusUpdates raises an exception."""
    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE
    mock_requests.post.return_value = mock_login

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_SELF
    mock_requests.get.return_value = mock_properties

    client = EmeraldHWS("test@example.com", "password")
    mocker.patch.object(client._connection_event, "wait", return_value=True)
    client.connect()

    # Make MQTT client None to simulate connection issue during status request
    mocker.patch.object(
        client, "requestAllStatusUpdates", side_effect=Exception("Connection lost")
    )

    # Reconnect should not raise
    client.reconnectMQTT()

    # MQTT client should still be set up and connection healthy
    assert client.mqttClient is not None
    assert client._is_connected is True


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


def test_disconnect_stops_mqtt_and_cancels_timers(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """Test that disconnect() stops the MQTT client and cancels all timers."""
    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE
    mock_requests.post.return_value = mock_login

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_SELF
    mock_requests.get.return_value = mock_properties

    client = EmeraldHWS("test@example.com", "password")
    mocker.patch.object(client._connection_event, "wait", return_value=True)
    client.connect()

    # Verify timers and client are active after connect
    assert client.mqttClient is not None
    assert client._is_connected is True
    assert client.reconnect_timer is not None
    assert client.health_check_timer is not None

    # Capture MQTT client reference before disconnect clears it
    mqtt_client = client.mqttClient

    # Disconnect
    client.disconnect()

    # Verify stop() was called on the underlying MQTT client
    mqtt_client.stop.assert_called_once()

    # Verify everything is cleaned up
    assert client.mqttClient is None
    assert client._is_connected is False
    assert client.reconnect_timer is None
    assert client.health_check_timer is None


def test_disconnect_handles_missing_client_gracefully(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """Test that disconnect() works even if MQTT client is already None."""
    client = EmeraldHWS("test@example.com", "password")

    # Should not raise even when nothing is connected
    client.disconnect()

    assert client.mqttClient is None
    assert client._is_connected is False
