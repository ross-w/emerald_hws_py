"""Tests for thread-safe state management."""
import copy
import pytest
import threading
import time
from unittest.mock import Mock
from emerald_hws import EmeraldHWS
from .conftest import MOCK_PROPERTY_RESPONSE_SELF, MQTT_MSG_TEMP_UPDATE, MQTT_MSG_SWITCH_OFF, MQTT_MSG_WORK_STATE_HEATING


def test_update_hws_state():
    """Test updating HWS state by ID and key."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = MOCK_PROPERTY_RESPONSE_SELF["info"]["property"]

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # Update temperature
    client.updateHWSState(hws_id, "temp_current", 55)

    # Verify state was updated
    hws = client.properties[0]["heat_pump"][0]
    assert hws["last_state"]["temp_current"] == 55


def test_update_hws_state_invokes_callback():
    """Test that callback is invoked when state is updated."""
    callback_count = []

    def test_callback():
        callback_count.append(1)

    client = EmeraldHWS("test@example.com", "password", update_callback=test_callback)
    client.properties = MOCK_PROPERTY_RESPONSE_SELF["info"]["property"]

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # Update state
    client.updateHWSState(hws_id, "temp_current", 55)

    # Verify callback was called
    assert len(callback_count) == 1




def test_multiple_heat_pumps_state_isolation():
    """Test that state updates are isolated between different heat pumps."""
    from copy import deepcopy

    client = EmeraldHWS("test@example.com", "password")

    # Create a property with two heat pumps
    property_data = deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"][0])
    hws1 = property_data["heat_pump"][0]
    hws2 = deepcopy(hws1)
    hws2["id"] = "hws-2222-bbbb-3333-cccc"
    property_data["heat_pump"].append(hws2)

    client.properties = [property_data]

    # Update first HWS
    client.updateHWSState("hws-1111-aaaa-2222-bbbb", "temp_current", 50)

    # Update second HWS
    client.updateHWSState("hws-2222-bbbb-3333-cccc", "temp_current", 65)

    # Verify states are isolated
    assert client.properties[0]["heat_pump"][0]["last_state"]["temp_current"] == 50
    assert client.properties[0]["heat_pump"][1]["last_state"]["temp_current"] == 65


def test_callback_not_required():
    """Test that callback is optional (can be None)."""
    client = EmeraldHWS("test@example.com", "password", update_callback=None)
    client.properties = MOCK_PROPERTY_RESPONSE_SELF["info"]["property"]

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # This should not raise an exception
    client.updateHWSState(hws_id, "temp_current", 55)

    # Verify state was still updated
    hws = client.properties[0]["heat_pump"][0]
    assert hws["last_state"]["temp_current"] == 55


def test_state_updates_from_mqtt_messages():
    """Test that MQTT messages properly update state via updateHWSState."""
    callback_calls = []

    def test_callback():
        callback_calls.append(True)

    client = EmeraldHWS("test@example.com", "password", update_callback=test_callback)
    client.properties = MOCK_PROPERTY_RESPONSE_SELF["info"]["property"]

    # Process MQTT message
    topic = "ep/heat_pump/from_gw/hws-1111-aaaa-2222-bbbb"
    client.mqttDecodeUpdate(topic, MQTT_MSG_TEMP_UPDATE)

    # Verify state was updated and callback invoked
    hws = client.properties[0]["heat_pump"][0]
    assert hws["last_state"]["temp_current"] == 59
    assert len(callback_calls) == 1


def test_mqtt_state_reflected_in_queries():
    """Test that MQTT updates are immediately reflected in query methods."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client._is_connected = True

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # Set initial state to on and normal mode
    client.properties[0]["heat_pump"][0]["last_state"]["switch"] = "on"
    client.properties[0]["heat_pump"][0]["last_state"]["mode"] = 1  # Normal mode
    assert client.isOn(hws_id) is True
    assert client.currentMode(hws_id) == 1

    # Receive MQTT update turning it off
    client.mqttDecodeUpdate(f"ep/heat_pump/from_gw/{hws_id}", MQTT_MSG_SWITCH_OFF)

    # Verify query methods reflect the change
    assert client.isOn(hws_id) is False

    # Receive MQTT update changing mode to boost
    boost_mode_msg = b'[{\n\t\t"msg_id":\t"123",\n\t\t"namespace":\t"business",\n\t\t"command":\t"upload_status",\n\t\t"direction":\t"gw2app",\n\t\t"property_id":\t"prop-aaaa-1111-bbbb-2222",\n\t\t"device_id":\t"hws-1111-aaaa-2222-bbbb"\n\t}, {\n\t\t"mode":\t0\n\t}]'
    client.mqttDecodeUpdate(f"ep/heat_pump/from_gw/{hws_id}", boost_mode_msg)

    # Verify mode change is reflected
    assert client.currentMode(hws_id) == 0


def test_heating_state_updates_consistency():
    """Test that heating state updates are consistent between MQTT and fallback logic."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client._is_connected = True

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # Initial state - not heating
    client.properties[0]["heat_pump"][0]["last_state"]["work_state"] = 0
    client.properties[0]["heat_pump"][0]["device_operation_status"] = 2
    assert client.isHeating(hws_id) is False

    # Receive MQTT update - starts heating
    client.mqttDecodeUpdate(f"ep/heat_pump/from_gw/{hws_id}", MQTT_MSG_WORK_STATE_HEATING)

    # Verify heating state is consistent
    assert client.isHeating(hws_id) is True

    # Check that both work_state and device_operation_status are considered
    status = client.getFullStatus(hws_id)
    assert status["last_state"]["work_state"] == 1


def test_callback_consistency_across_updates():
    """Test that callbacks are consistently invoked across state updates."""
    callback_log = []

    def test_callback():
        callback_log.append("updated")

    client = EmeraldHWS("test@example.com", "password", update_callback=test_callback)
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # Multiple MQTT updates
    client.mqttDecodeUpdate(f"ep/heat_pump/from_gw/{hws_id}", MQTT_MSG_TEMP_UPDATE)
    client.mqttDecodeUpdate(f"ep/heat_pump/from_gw/{hws_id}", MQTT_MSG_SWITCH_OFF)
    client.mqttDecodeUpdate(f"ep/heat_pump/from_gw/{hws_id}", MQTT_MSG_WORK_STATE_HEATING)

    # Verify callback invoked for each update
    assert len(callback_log) == 3

    # Verify all state changes were applied
    hws = client.properties[0]["heat_pump"][0]
    assert hws["last_state"]["temp_current"] == 59
    assert hws["last_state"]["switch"] == 0
    assert hws["last_state"]["work_state"] == 1
