"""Tests for gating MQTT operations on real connection state.

Regression cover for the bug where a control message sent during a live
disconnect went into the mqtt5 client's offline queue and, at QoS 1, blocked
the caller for the full 20s publish timeout before raising a bare TimeoutError.
The command was not dropped either: awscrt re-queues un-acked QoS 1 publishes,
so it could still arrive long after the caller was told it had failed.

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
    connect_and_clear_publishes,
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
    # Clears the startup comp_query so these gate assertions see only the
    # publish the test itself triggers.
    connect_and_clear_publishes(client)
    return client


def _simulate_disconnect(client, mocker, wait_results=(False, False)):
    """Simulate a live disconnect: socket down, setup still complete.

    This is the state on_lifecycle_disconnection leaves behind - it clears
    _connection_event but deliberately leaves _setup_complete True.

    :param wait_results: what each successive _connection_event.wait() returns.
        The gate waits once to give awscrt's auto-reconnect a chance, and again
        after its own reconnect, so (False, True) means "awscrt did not recover
        but our reconnect worked".
    :returns: the patched wait mock, for asserting call count and timeout
    """
    mocker.patch.object(client._connection_event, "is_set", return_value=False)
    return mocker.patch.object(
        client._connection_event, "wait", side_effect=list(wait_results)
    )


def test_control_message_during_disconnect_reconnects_and_fails_fast(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """The headline case: a control message sent while disconnected must
    trigger a reconnect and raise a typed error, rather than go into the
    offline queue to block for 20s and then possibly be delivered late."""
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
    reconnect.assert_called_once_with(reason="control_message", skip_if_connected=True)

    # Nothing was handed to the offline queue.
    mqtt_client.publish.assert_not_called()

    assert "MQTT connection unavailable" in str(exc_info.value)

    # Waits once before reconnecting and once after, each bounded at 5s -
    # never the 20s publish timeout this replaces.
    assert wait_mock.call_count == 2
    assert wait_mock.call_args_list == [
        mocker.call(timeout=5),
        mocker.call(timeout=5),
    ]
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
    """awscrt did not recover on its own, but our reconnect worked - the
    publish goes ahead with an unchanged payload."""
    client = _connected_client(mock_requests, mocker)
    mqtt_client = (
        mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    )

    _simulate_disconnect(client, mocker, wait_results=(False, True))
    reconnect = mocker.patch.object(client, "reconnectMQTT")

    client.turnOn(HWS_ID)

    reconnect.assert_called_once_with(reason="control_message", skip_if_connected=True)
    mqtt_client.publish.assert_called_once()

    publish_packet = mqtt_client.publish.call_args[0][0]
    assert publish_packet.topic == f"ep/heat_pump/to_gw/{HWS_ID}"
    header, payload = json.loads(publish_packet.payload)
    assert header["command"] == "control"
    assert header["device_id"] == HWS_ID
    assert payload == {"switch": 1}


def test_transient_blip_is_ridden_out_without_tearing_down_the_client(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """A brief drop clears _connection_event, but awscrt is already
    auto-reconnecting with backoff. The gate must wait for that rather than
    stop() the client mid-recovery and force a full rebuild."""
    client = _connected_client(mock_requests, mocker)
    mqtt_client = (
        mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    )
    mqtt_client.stop.reset_mock()

    wait_mock = _simulate_disconnect(client, mocker, wait_results=(True,))
    reconnect = mocker.patch.object(client, "reconnectMQTT")

    client.turnOn(HWS_ID)

    wait_mock.assert_called_once_with(timeout=5)
    reconnect.assert_not_called()
    mqtt_client.stop.assert_not_called()
    mqtt_client.publish.assert_called_once()


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

    wait_mock = _simulate_disconnect(client, mocker, wait_results=(False,))
    reconnect = mocker.patch.object(client, "reconnectMQTT")

    with pytest.raises(EmeraldConnectionError):
        client.requestStatusUpdate(HWS_ID)

    wait_mock.assert_called_once_with(timeout=5)
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


def test_iot_metrics_collection_is_disabled(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """awscrt's usage-metrics path must stay off.

    Building it breaks outright when two awscrt versions are loaded at once; see
    tests/test_native_bindings.py for why that happens under Home Assistant.
    """
    _connected_client(mock_requests, mocker)

    kwargs = mock_mqtt5_client_builder.websockets_with_default_aws_signing.call_args[1]
    assert kwargs["enable_metrics_collection"] is False


def test_reconnect_is_skipped_if_connection_restored_while_waiting_for_lock(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """Several threads can observe the same disconnect and queue on _mqtt_lock.
    The second one must not stop the healthy client the first just built - a
    QoS 1 publish already in flight on it would never get its PUBACK."""
    client = _connected_client(mock_requests, mocker)
    mqtt_client = (
        mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    )
    mqtt_client.stop.reset_mock()

    # is_set() is True: the connection came back before we got the lock.
    client.reconnectMQTT(reason="control_message", skip_if_connected=True)

    mqtt_client.stop.assert_not_called()


def test_scheduled_reconnect_still_rebuilds_a_healthy_connection(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """The skip must be opt-in: the 12-hourly refresh and the health check
    rebuild deliberately, while the connection is up."""
    client = _connected_client(mock_requests, mocker)
    mqtt_client = (
        mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    )
    mqtt_client.stop.reset_mock()

    client.reconnectMQTT(reason="scheduled")

    mqtt_client.stop.assert_called_once()


def test_failed_reconnect_raises_typed_error(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """connectMQTT makes live Cognito calls, which are likely to fail during
    the outage that triggered the gate. Callers must not see botocore types."""
    client = _connected_client(mock_requests, mocker)

    _simulate_disconnect(client, mocker, wait_results=(False,))
    mocker.patch.object(
        client,
        "reconnectMQTT",
        side_effect=RuntimeError("botocore: could not connect to endpoint"),
    )

    with pytest.raises(EmeraldConnectionError) as exc_info:
        client.turnOn(HWS_ID)

    assert "Unable to reconnect to MQTT" in str(exc_info.value)
    assert isinstance(exc_info.value, EmeraldError)


def test_scheduled_reconnect_reschedules_itself_after_a_failure(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """A failed reconnect must never kill the timer - without the reschedule
    the process would never reconnect again for the rest of its life."""
    client = _connected_client(mock_requests, mocker)
    mocker.patch.object(
        client, "reconnectMQTT", side_effect=RuntimeError("network unreachable")
    )
    client.reconnect_timer = None

    client.scheduled_reconnect()

    assert client.reconnect_timer is not None
    assert client.reconnect_timer.is_alive()
    client.reconnect_timer.cancel()


def test_health_check_reschedules_itself_after_a_failed_reconnect(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """Same for the health check, which is the shorter of the two timers and
    so the one recovery normally depends on."""
    client = _connected_client(mock_requests, mocker)
    mocker.patch.object(
        client, "reconnectMQTT", side_effect=RuntimeError("network unreachable")
    )
    # Force the "no messages for too long, reconnect" branch.
    client.last_message_time = time.time() - (client.health_check_interval + 1)
    client.connection_state = "connected"
    client.health_check_timer = None

    client.check_connection_health()

    assert client.health_check_timer is not None
    assert client.health_check_timer.is_alive()
    client.health_check_timer.cancel()


def test_exception_hierarchy():
    """EmeraldTimeoutError must keep subclassing the builtin TimeoutError -
    the consuming integration catches that before its broad Exception arm."""
    assert issubclass(EmeraldConnectionError, EmeraldError)
    assert issubclass(EmeraldTimeoutError, EmeraldError)
    assert issubclass(EmeraldTimeoutError, TimeoutError)
    assert not issubclass(EmeraldConnectionError, TimeoutError)
    # Everything stays catchable by callers using broad `except Exception`.
    assert issubclass(EmeraldError, Exception)
