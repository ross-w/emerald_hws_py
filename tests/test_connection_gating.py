"""Tests for gating MQTT operations on real connection state.

Regression cover for the bug where a control message sent during a live
disconnect went into the mqtt5 client's offline queue and, at QoS 1, blocked
the caller for the full 20s publish timeout before raising a bare TimeoutError
- with the command never delivered.

The guard that was supposed to prevent this read _setup_complete (then named
_is_connected), which is deliberately never cleared on a transient disconnect,
so it was dead code. The gate now reads _connection_event instead.
"""

import json
import time
from concurrent.futures import TimeoutError as FuturesTimeoutError
from unittest.mock import Mock

import pytest

from emerald_hws import (
    EmeraldConnectionError,
    EmeraldError,
    EmeraldHWS,
    EmeraldTimeoutError,
)
from .conftest import (
    MOCK_LOGIN_RESPONSE,
    MOCK_PROPERTY_RESPONSE_SELF,
    mark_connected,
)

HWS_ID = "hws-1111-aaaa-2222-bbbb"


def _connected_client(mock_requests, mocker):
    """Build a client that has completed connect() and believes it is live."""
    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE
    mock_requests.post.return_value = mock_login

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_SELF
    mock_requests.get.return_value = mock_properties

    client = EmeraldHWS("test@example.com", "password")
    mark_connected(client, mocker)
    client.connect()
    return client


def _simulate_disconnect(client, mocker, comes_back=False):
    """Simulate a live disconnect: socket down, setup still complete.

    This is the state on_lifecycle_disconnection leaves behind - it clears
    _connection_event but deliberately leaves _setup_complete True.

    :param comes_back: whether the subsequent wait() should report success
    :returns: the patched wait mock, for asserting the timeout used
    """
    mocker.patch.object(client._connection_event, "is_set", return_value=False)
    return mocker.patch.object(
        client._connection_event, "wait", return_value=comes_back
    )


def test_control_message_during_disconnect_reconnects_and_fails_fast(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """The headline case: a control message sent while disconnected must
    trigger a reconnect and raise a typed error, not block for 20s in the
    offline queue waiting for a PUBACK that will never arrive."""
    client = _connected_client(mock_requests, mocker)
    mqtt_client = (
        mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    )

    wait_mock = _simulate_disconnect(client, mocker)
    reconnect = mocker.patch.object(client, "reconnectMQTT")

    started = time.monotonic()
    with pytest.raises(EmeraldConnectionError) as exc_info:
        client.turnOn(HWS_ID)
    elapsed = time.monotonic() - started

    # Reconnects via reconnectMQTT, NOT connect() - connect() would stand up a
    # competing MQTT connection with duplicate timers.
    reconnect.assert_called_once_with(reason="control_message")

    # Nothing was handed to the offline queue.
    mqtt_client.publish.assert_not_called()

    assert "MQTT connection unavailable" in str(exc_info.value)

    # The wait is bounded at 5s, not the 20s publish timeout it replaces.
    wait_mock.assert_called_once_with(timeout=5)
    assert elapsed < 5


def test_control_message_publishes_normally_when_connected(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """Happy path regression guard: a live connection must not reconnect."""
    client = _connected_client(mock_requests, mocker)
    mqtt_client = (
        mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    )
    reconnect = mocker.patch.object(client, "reconnectMQTT")

    client.turnOn(HWS_ID)

    reconnect.assert_not_called()
    mqtt_client.publish.assert_called_once()


def test_control_message_publishes_after_successful_reconnect(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """When the reconnect brings the connection back, the publish goes ahead
    with an unchanged payload."""
    client = _connected_client(mock_requests, mocker)
    mqtt_client = (
        mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    )

    _simulate_disconnect(client, mocker, comes_back=True)
    reconnect = mocker.patch.object(client, "reconnectMQTT")

    client.turnOn(HWS_ID)

    reconnect.assert_called_once_with(reason="control_message")
    mqtt_client.publish.assert_called_once()

    publish_packet = mqtt_client.publish.call_args[0][0]
    assert publish_packet.topic == f"ep/heat_pump/to_gw/{HWS_ID}"
    header, payload = json.loads(publish_packet.payload)
    assert header["command"] == "control"
    assert header["device_id"] == HWS_ID
    assert payload == {"switch": 1}


def test_status_update_during_disconnect_does_not_reconnect(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """requestStatusUpdate is reachable from inside reconnectMQTT (via
    _request_status_updates_safe), so its gate must never reconnect - that
    would have a reconnect re-enter itself, once per thread-pool worker."""
    client = _connected_client(mock_requests, mocker)
    mqtt_client = (
        mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    )

    _simulate_disconnect(client, mocker)
    reconnect = mocker.patch.object(client, "reconnectMQTT")

    with pytest.raises(EmeraldConnectionError):
        client.requestStatusUpdate(HWS_ID)

    reconnect.assert_not_called()
    mqtt_client.publish.assert_not_called()


def test_status_update_publishes_normally_when_connected(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """The wait-only gate must not break the normal status refresh."""
    client = _connected_client(mock_requests, mocker)
    mqtt_client = (
        mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    )

    client.requestStatusUpdate(HWS_ID)

    mqtt_client.publish.assert_called_once()
    header, _ = json.loads(mqtt_client.publish.call_args[0][0].payload)
    assert header["command"] == "comp_query"


@pytest.mark.parametrize("raised", [FuturesTimeoutError, TimeoutError])
def test_publish_timeout_becomes_emerald_timeout_error(
    raised,
    mock_requests,
    mock_boto3,
    mock_mqtt5_client_builder,
    mock_auth,
    mock_io,
    mocker,
):
    """A publish timeout must surface as EmeraldTimeoutError, which still
    subclasses the builtin TimeoutError so the consuming Home Assistant
    integration's `except TimeoutError` arm keeps working unchanged.

    concurrent.futures.TimeoutError is only an alias of the builtin on Python
    3.11+, so both are exercised.
    """
    client = _connected_client(mock_requests, mocker)
    mqtt_client = (
        mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    )
    mqtt_client.publish.return_value = Mock(result=Mock(side_effect=raised()))

    with pytest.raises(EmeraldTimeoutError) as exc_info:
        client.turnOn(HWS_ID)

    assert isinstance(exc_info.value, TimeoutError)
    assert isinstance(exc_info.value, EmeraldError)
    assert HWS_ID in str(exc_info.value)


def test_publish_transport_error_becomes_emerald_connection_error(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """Non-timeout transport failures must not leak to callers either."""
    client = _connected_client(mock_requests, mocker)
    mqtt_client = (
        mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    )
    mqtt_client.publish.return_value = Mock(
        result=Mock(side_effect=RuntimeError("aws-crt exploded"))
    )

    with pytest.raises(EmeraldConnectionError) as exc_info:
        client.turnOn(HWS_ID)

    assert "aws-crt exploded" in str(exc_info.value)


def test_subscribe_timeout_becomes_emerald_timeout_error(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """The subscribe future is wrapped too."""
    mqtt_client = (
        mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    )
    mqtt_client.subscribe.return_value = Mock(
        result=Mock(side_effect=FuturesTimeoutError())
    )

    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE
    mock_requests.post.return_value = mock_login
    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_SELF
    mock_requests.get.return_value = mock_properties

    client = EmeraldHWS("test@example.com", "password")
    mark_connected(client, mocker)

    with pytest.raises(EmeraldTimeoutError) as exc_info:
        client.connect()

    assert isinstance(exc_info.value, TimeoutError)
    assert HWS_ID in str(exc_info.value)
    # Setup did not complete, so a later call will retry it.
    assert not client._setup_complete


def test_missing_hws_raises_typed_error(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """The unknown-device error is typed, with its message preserved."""
    client = _connected_client(mock_requests, mocker)

    with pytest.raises(EmeraldError) as exc_info:
        client.turnOn("no-such-hws")

    assert "Unable to find HWS" in str(exc_info.value)


def test_keep_alive_interval_is_sixty_seconds(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """The aws-crt default is 20 minutes, which lets a half-open socket go
    undetected for that long. AWS IoT accepts 30-1200s."""
    _connected_client(mock_requests, mocker)

    kwargs = mock_mqtt5_client_builder.websockets_with_default_aws_signing.call_args[1]
    assert kwargs["keep_alive_interval_sec"] == 60


def test_exception_hierarchy():
    """EmeraldTimeoutError must keep subclassing the builtin TimeoutError -
    the consuming integration catches that before its broad Exception arm."""
    assert issubclass(EmeraldConnectionError, EmeraldError)
    assert issubclass(EmeraldTimeoutError, EmeraldError)
    assert issubclass(EmeraldTimeoutError, TimeoutError)
    assert not issubclass(EmeraldConnectionError, TimeoutError)
    # Everything stays catchable by callers using broad `except Exception`.
    assert issubclass(EmeraldError, Exception)
