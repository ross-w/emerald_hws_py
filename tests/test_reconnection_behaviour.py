"""Tests for reconnection behaviour and state persistence."""

import json
from unittest.mock import Mock
from emerald_hws import EmeraldHWS
from .conftest import (
    MOCK_LOGIN_RESPONSE,
    MOCK_PROPERTY_RESPONSE_MIXED,
    MOCK_PROPERTY_RESPONSE_SELF,
    mark_connected,
)


def _mock_api(mock_requests, property_response=MOCK_PROPERTY_RESPONSE_SELF):
    """Point the mocked REST layer at a login and a property list."""
    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE
    mock_requests.post.return_value = mock_login

    mock_properties = Mock()
    mock_properties.json.return_value = property_response
    mock_requests.get.return_value = mock_properties


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
    mark_connected(client, mocker)

    assert not client._setup_complete

    # Attempt operation - should auto-connect
    hws_id = "hws-1111-aaaa-2222-bbbb"
    client.turnOn(hws_id)

    # Verify auto-connection occurred
    assert client._setup_complete
    assert mock_boto3.client.called
    assert mock_mqtt5_client_builder.websockets_with_default_aws_signing.called


def test_status_requested_via_mqtt_on_initial_connect(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """Test that connect() sends a comp_query to every HWS it discovers.

    getAllHWS() seeds last_state from the REST API, which now lags behind what
    the device reports over MQTT. connect() therefore does what reconnectMQTT
    already did and asks each device for its live status, so a fresh session is
    not left showing stale values until the next unsolicited upload_status.
    """
    _mock_api(mock_requests, MOCK_PROPERTY_RESPONSE_MIXED)

    client = EmeraldHWS("test@example.com", "password")
    mark_connected(client, mocker)
    client.connect()

    mqtt_client = (
        mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    )

    # One comp_query per heat pump - the self-owned one and the shared one.
    expected = {
        "hws-1111-aaaa-2222-bbbb": ("prop-aaaa-1111-bbbb-2222", "aabbccddeeff"),
        "hws-9999-eeee-8888-ffff": ("prop-9999-eeee-8888-ffff", "112233445566"),
    }
    assert mqtt_client.publish.call_count == len(expected)

    seen = {}
    for call in mqtt_client.publish.call_args_list:
        packet = call[0][0]
        header, body = json.loads(packet.payload)
        assert header["command"] == "comp_query"
        assert header["direction"] == "app2gw"
        assert header["namespace"] == "business"
        assert body == {}
        assert packet.topic == "ep/heat_pump/to_gw/{}".format(header["device_id"])
        seen[header["device_id"]] = (header["property_id"], header["hw_id"])

    assert seen == expected


def test_status_not_requested_again_on_redundant_connect(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """Test that a second connect() on a live client sends no further comp_query.

    connect() is called lazily from getFullStatus/listHWS on every cold read, so
    the refresh must sit behind the _setup_complete early return - otherwise
    routine reads would fan out a comp_query burst each time.
    """
    _mock_api(mock_requests)

    client = EmeraldHWS("test@example.com", "password")
    mark_connected(client, mocker)
    client.connect()

    mqtt_client = (
        mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    )
    assert mqtt_client.publish.call_count == 1
    mqtt_client.publish.reset_mock()

    client.connect()

    mqtt_client.publish.assert_not_called()


def test_status_request_failure_on_initial_connect_is_non_fatal(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """Test that connect() still completes when the startup comp_query fails.

    A device that is offline at startup must not stop the client being usable -
    the refresh is best-effort, swallowed by _request_status_updates_safe.
    """
    _mock_api(mock_requests)

    mqtt_client = (
        mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    )
    mqtt_client.publish.return_value.result.side_effect = Exception(
        "MQTT publish failed"
    )

    client = EmeraldHWS("test@example.com", "password")
    mark_connected(client, mocker)

    client.connect()

    assert client._setup_complete is True
    assert client.mqttClient is not None
    # Subscriptions and timers were still set up before the failed refresh.
    mqtt_client.subscribe.assert_called_once()
    assert client.reconnect_timer is not None
    assert client.health_check_timer is not None
    client.reconnect_timer.cancel()
    client.health_check_timer.cancel()


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
    mark_connected(client, mocker)
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

    # Verify the payload is a comp_query with correct device details
    publish_calls_after = mqtt_client.publish.call_args_list[
        publish_count_after_connect:
    ]
    assert len(publish_calls_after) >= 1

    packet = publish_calls_after[0][0][0]  # first new call, positional arg
    assert packet.topic == "ep/heat_pump/to_gw/hws-1111-aaaa-2222-bbbb"
    payload = json.loads(packet.payload)
    assert payload[0]["command"] == "comp_query"
    assert payload[0]["device_id"] == "hws-1111-aaaa-2222-bbbb"
    assert payload[0]["property_id"] == "prop-aaaa-1111-bbbb-2222"
    assert payload[0]["hw_id"] == "aabbccddeeff"
    assert payload[0]["direction"] == "app2gw"
    assert payload[1] == {}


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
    mark_connected(client, mocker)
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
    assert client._setup_complete is True


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
    mark_connected(client, mocker)
    client.connect()

    # Make MQTT client None to simulate connection issue during status request
    mocker.patch.object(
        client, "requestAllStatusUpdates", side_effect=Exception("Connection lost")
    )

    # Reconnect should not raise
    client.reconnectMQTT()

    # MQTT client should still be set up and connection healthy
    assert client.mqttClient is not None
    assert client._setup_complete is True


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
    mark_connected(client, mocker)
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
    mark_connected(client, mocker)
    client.connect()

    # Verify timers and client are active after connect
    assert client.mqttClient is not None
    assert client._setup_complete is True
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
    assert client._setup_complete is False
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
    assert client._setup_complete is False
