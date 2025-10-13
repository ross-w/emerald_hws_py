"""Integration tests for end-to-end behavioural flows."""

from unittest.mock import Mock
from emerald_hws import EmeraldHWS
from .conftest import (
    MOCK_LOGIN_RESPONSE,
    MOCK_PROPERTY_RESPONSE_SELF,
    MOCK_PROPERTY_RESPONSE_SHARED,
    MQTT_MSG_TEMP_UPDATE,
    MQTT_MSG_SWITCH_OFF,
    MQTT_MSG_SWITCH_ON,
)


def test_complete_login_to_mqtt_flow(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """Test complete user flow: login → get properties → connect MQTT → receive updates."""
    # Setup mocks
    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE
    mock_requests.post.return_value = mock_login

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_SELF
    mock_requests.get.return_value = mock_properties

    # Execute complete flow
    callback_calls = []

    def test_callback():
        callback_calls.append(True)

    client = EmeraldHWS("test@example.com", "password", update_callback=test_callback)
    mocker.patch.object(client._connection_event, "wait", return_value=True)

    # Connect - this should: login → get properties → connect MQTT → subscribe
    client.connect()

    # Verify the flow worked
    assert client._is_connected
    assert len(client.properties) == 1
    assert client.properties[0]["property_type"] == "Self"

    # Simulate MQTT update
    topic = "ep/heat_pump/from_gw/hws-1111-aaaa-2222-bbbb"
    client.mqttDecodeUpdate(topic, MQTT_MSG_TEMP_UPDATE)

    # Verify state was updated and callback invoked
    hws = client.properties[0]["heat_pump"][0]
    assert hws["last_state"]["temp_current"] == 59
    assert len(callback_calls) == 1


def test_control_command_with_mqtt_response(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """Test end-to-end control flow: send command → receive MQTT response → verify state change."""
    # Setup mocks
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

    # Initially on
    client.properties[0]["heat_pump"][0]["last_state"]["switch"] = "on"
    assert client.isOn(hws_id) is True

    # Send turn off command
    client.turnOff(hws_id)

    # Simulate MQTT response
    topic = f"ep/heat_pump/from_gw/{hws_id}"
    client.mqttDecodeUpdate(topic, MQTT_MSG_SWITCH_OFF)

    # Verify state changed
    assert client.isOn(hws_id) is False


def test_shared_property_integration_flow(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """Test integration flow with shared_property (customer account scenario)."""
    # Setup mocks for shared property response

    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE
    mock_requests.post.return_value = mock_login

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_SHARED
    mock_requests.get.return_value = mock_properties

    # Execute flow
    client = EmeraldHWS("customer@example.com", "password")
    mocker.patch.object(client._connection_event, "wait", return_value=True)

    client.connect()

    # Verify shared property flow works
    assert client._is_connected
    assert len(client.properties) == 1
    assert client.properties[0]["property_type"] == "Shared"
    assert client.properties[0]["heat_pump"][0]["id"] == "hws-9999-eeee-8888-ffff"

    # Test control works on shared property
    hws_id = "hws-9999-eeee-8888-ffff"
    client.turnOn(hws_id)
    client.mqttDecodeUpdate(f"ep/heat_pump/from_gw/{hws_id}", MQTT_MSG_SWITCH_ON)

    assert client.isOn(hws_id) is True


def test_mixed_properties_integration(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """Test integration with both self and shared properties."""
    from .conftest import MOCK_PROPERTY_RESPONSE_MIXED

    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE
    mock_requests.post.return_value = mock_login

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_MIXED
    mock_requests.get.return_value = mock_properties

    # Execute
    client = EmeraldHWS("user@example.com", "password")
    mocker.patch.object(client._connection_event, "wait", return_value=True)

    client.connect()

    # Verify both properties are accessible
    assert len(client.properties) == 2
    hws_ids = client.listHWS()
    assert "hws-1111-aaaa-2222-bbbb" in hws_ids  # Self property
    assert "hws-9999-eeee-8888-ffff" in hws_ids  # Shared property

    # Test independent control of each HWS
    self_hws = "hws-1111-aaaa-2222-bbbb"
    shared_hws = "hws-9999-eeee-8888-ffff"

    # Control self HWS and simulate MQTT response
    client.setBoostMode(self_hws)
    boost_mode_response = b'[{\n\t\t"msg_id":\t"123",\n\t\t"namespace":\t"business",\n\t\t"command":\t"upload_status",\n\t\t"direction":\t"gw2app",\n\t\t"property_id":\t"prop-aaaa-1111-bbbb-2222",\n\t\t"device_id":\t"hws-1111-aaaa-2222-bbbb"\n\t}, {\n\t\t"mode":\t0\n\t}]'
    client.mqttDecodeUpdate(f"ep/heat_pump/from_gw/{self_hws}", boost_mode_response)
    assert client.currentMode(self_hws) == 0

    # Control shared HWS and simulate MQTT response
    client.setQuietMode(shared_hws)
    quiet_mode_response = b'[{\n\t\t"msg_id":\t"456",\n\t\t"namespace":\t"business",\n\t\t"command":\t"upload_status",\n\t\t"direction":\t"gw2app",\n\t\t"property_id":\t"prop-9999-eeee-8888-ffff",\n\t\t"device_id":\t"hws-9999-eeee-8888-ffff"\n\t}, {\n\t\t"mode":\t2\n\t}]'
    client.mqttDecodeUpdate(f"ep/heat_pump/from_gw/{shared_hws}", quiet_mode_response)
    assert client.currentMode(shared_hws) == 2


def test_state_persistence_through_reconnection(
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mocker
):
    """Test that state persists during MQTT reconnection."""
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

    # Set some initial state via MQTT
    client.mqttDecodeUpdate(f"ep/heat_pump/from_gw/{hws_id}", MQTT_MSG_TEMP_UPDATE)
    client.mqttDecodeUpdate(f"ep/heat_pump/from_gw/{hws_id}", MQTT_MSG_SWITCH_ON)
    initial_temp = client.properties[0]["heat_pump"][0]["last_state"]["temp_current"]
    assert initial_temp == 59

    # Simulate reconnection (create new MQTT client)
    old_mqtt_client = (
        mock_mqtt5_client_builder.websockets_with_default_aws_signing.return_value
    )
    client.reconnectMQTT()

    # Verify old client was stopped and new created
    old_mqtt_client.stop.assert_called()
    assert mock_mqtt5_client_builder.websockets_with_default_aws_signing.call_count >= 2

    # Verify state persisted through reconnection
    assert client.properties[0]["heat_pump"][0]["last_state"]["temp_current"] == 59
    assert client.properties[0]["heat_pump"][0]["last_state"]["switch"] == 1
    assert client.isOn(hws_id) is True  # Should still work
