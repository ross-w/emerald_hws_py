"""Tests for MQTT operations."""

import pytest
from emerald_hws import EmeraldHWS
from .conftest import (
    MOCK_LOGIN_RESPONSE,
    MOCK_PROPERTY_RESPONSE_SELF,
    MOCK_COGNITO_IDENTITY,
    MQTT_MSG_TEMP_UPDATE,
    MQTT_MSG_SWITCH_OFF,
    MQTT_MSG_SWITCH_ON,
    MQTT_MSG_WORK_STATE_HEATING,
    MQTT_MSG_WORK_STATE_IDLE,
)


def get_hws(client):
    """Helper to get first heat pump from client properties."""
    return client.properties[0]["heat_pump"][0]


def test_mqtt_message_parsing_temp_update(mqtt_client_with_properties):
    """Test parsing of temperature update MQTT message."""
    client = mqtt_client_with_properties["client"]
    topic = mqtt_client_with_properties["topic"]

    # Decode the message
    client.mqttDecodeUpdate(topic, MQTT_MSG_TEMP_UPDATE)

    # Verify state was updated
    assert get_hws(client)["last_state"]["temp_current"] == 59


def test_mqtt_message_parsing_switch_state(mqtt_client_with_properties):
    """Test parsing of switch state MQTT messages."""
    client = mqtt_client_with_properties["client"]
    topic = mqtt_client_with_properties["topic"]

    # Test switch off
    client.mqttDecodeUpdate(topic, MQTT_MSG_SWITCH_OFF)
    assert get_hws(client)["last_state"]["switch"] == 0

    # Test switch on
    client.mqttDecodeUpdate(topic, MQTT_MSG_SWITCH_ON)
    assert get_hws(client)["last_state"]["switch"] == 1


def test_mqtt_message_parsing_work_state(mqtt_client_with_properties):
    """Test parsing of work_state MQTT messages."""
    client = mqtt_client_with_properties["client"]
    topic = mqtt_client_with_properties["topic"]

    # Test work_state heating
    client.mqttDecodeUpdate(topic, MQTT_MSG_WORK_STATE_HEATING)
    assert get_hws(client)["last_state"]["work_state"] == 1

    # Test work_state idle
    client.mqttDecodeUpdate(topic, MQTT_MSG_WORK_STATE_IDLE)
    assert get_hws(client)["last_state"]["work_state"] == 0


def test_mqtt_callback_invoked_on_message():
    """Test that update callback is invoked when MQTT message received."""
    callback_called = []

    def test_callback():
        callback_called.append(True)

    client = EmeraldHWS("test@example.com", "password", update_callback=test_callback)

    # Setup initial state
    client.properties = MOCK_PROPERTY_RESPONSE_SELF["info"]["property"]

    # Process a message
    topic = "ep/heat_pump/from_gw/hws-1111-aaaa-2222-bbbb"
    client.mqttDecodeUpdate(topic, MQTT_MSG_TEMP_UPDATE)

    # Verify callback was called
    assert len(callback_called) == 1
