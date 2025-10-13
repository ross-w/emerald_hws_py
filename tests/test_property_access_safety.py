"""Tests for safe property access and edge cases.

These tests ensure the module handles API changes gracefully, such as:
- Missing or None values in expected fields
- Type variations (switch can be 1, "on", or 0)
- Empty or malformed data structures

These are regression tests to prevent crashes when the API returns unexpected data.
"""
import copy
import pytest
from emerald_hws import EmeraldHWS
from .conftest import MOCK_PROPERTY_RESPONSE_SELF


def test_is_on_handles_missing_last_state():
    """Test that isOn() handles missing last_state gracefully."""
    client = EmeraldHWS("test@example.com", "password")
    client._is_connected = True

    # Create property with no last_state
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client.properties[0]["heat_pump"][0]["last_state"] = None

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # Should return False, not crash
    assert client.isOn(hws_id) is False


def test_is_on_handles_missing_switch_key():
    """Test that isOn() handles missing 'switch' key in last_state."""
    client = EmeraldHWS("test@example.com", "password")
    client._is_connected = True

    # Create property with last_state but no switch key
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    del client.properties[0]["heat_pump"][0]["last_state"]["switch"]

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # Should return False, not crash
    assert client.isOn(hws_id) is False


def test_is_on_handles_numeric_switch():
    """Test that isOn() correctly handles switch=1 (numeric)."""
    client = EmeraldHWS("test@example.com", "password")
    client._is_connected = True
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # Test with numeric 1
    client.properties[0]["heat_pump"][0]["last_state"]["switch"] = 1
    assert client.isOn(hws_id) is True

    # Test with numeric 0
    client.properties[0]["heat_pump"][0]["last_state"]["switch"] = 0
    assert client.isOn(hws_id) is False


def test_is_on_handles_string_switch():
    """Test that isOn() correctly handles switch="on" (string)."""
    client = EmeraldHWS("test@example.com", "password")
    client._is_connected = True
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # Test with string "on"
    client.properties[0]["heat_pump"][0]["last_state"]["switch"] = "on"
    assert client.isOn(hws_id) is True

    # Test with string "off"
    client.properties[0]["heat_pump"][0]["last_state"]["switch"] = "off"
    assert client.isOn(hws_id) is False


def test_is_heating_handles_missing_work_state():
    """Test that isHeating() falls back to device_operation_status when work_state missing."""
    client = EmeraldHWS("test@example.com", "password")
    client._is_connected = True
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # Remove work_state to test fallback
    client.properties[0]["heat_pump"][0]["last_state"].pop("work_state", None)

    # Set device_operation_status to heating
    client.properties[0]["heat_pump"][0]["device_operation_status"] = 1
    assert client.isHeating(hws_id) is True

    # Set device_operation_status to not heating
    client.properties[0]["heat_pump"][0]["device_operation_status"] = 2
    assert client.isHeating(hws_id) is False


def test_is_heating_handles_no_status_fields():
    """Test that isHeating() handles missing both work_state and device_operation_status."""
    client = EmeraldHWS("test@example.com", "password")
    client._is_connected = True
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # Remove work_state
    client.properties[0]["heat_pump"][0]["last_state"].pop("work_state", None)

    # Remove device_operation_status
    client.properties[0]["heat_pump"][0].pop("device_operation_status", None)

    # Should return False, not crash
    assert client.isHeating(hws_id) is False


def test_current_mode_handles_missing_mode():
    """Test that currentMode() handles missing mode gracefully."""
    client = EmeraldHWS("test@example.com", "password")
    client._is_connected = True
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # Remove mode from last_state
    del client.properties[0]["heat_pump"][0]["last_state"]["mode"]

    # Should return None, not crash
    assert client.currentMode(hws_id) is None


def test_get_hourly_energy_usage_handles_none_consumption_data():
    """Test that getHourlyEnergyUsage() handles None consumption_data."""
    client = EmeraldHWS("test@example.com", "password")
    client._is_connected = True
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # Set consumption_data to None
    client.properties[0]["heat_pump"][0]["consumption_data"] = None

    # Should return None, not crash
    assert client.getHourlyEnergyUsage(hws_id) is None


def test_get_hourly_energy_usage_handles_malformed_json():
    """Test that getHourlyEnergyUsage() handles malformed JSON in consumption_data."""
    import json as json_module

    client = EmeraldHWS("test@example.com", "password")
    client._is_connected = True
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # Set consumption_data to invalid JSON string
    client.properties[0]["heat_pump"][0]["consumption_data"] = "not valid json"

    # Should raise a JSONDecodeError
    with pytest.raises(json_module.JSONDecodeError):
        client.getHourlyEnergyUsage(hws_id)


def test_get_hourly_energy_usage_handles_missing_fields():
    """Test that getHourlyEnergyUsage() handles missing current_hour or last_data_at."""
    import json

    client = EmeraldHWS("test@example.com", "password")
    client._is_connected = True
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # Set consumption_data with missing fields
    incomplete_data = {"past_seven_days": {}}
    client.properties[0]["heat_pump"][0]["consumption_data"] = json.dumps(incomplete_data)

    # Should return None, not crash
    assert client.getHourlyEnergyUsage(hws_id) is None


def test_get_info_handles_missing_fields():
    """Test that getInfo() handles devices with missing optional fields."""
    client = EmeraldHWS("test@example.com", "password")
    client._is_connected = True
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # Remove some fields
    del client.properties[0]["heat_pump"][0]["serial_number"]
    del client.properties[0]["heat_pump"][0]["brand"]

    # Should still return dict with None values, not crash
    info = client.getInfo(hws_id)
    assert info is not None
    assert info["id"] == hws_id
    assert info["serial_number"] is None
    assert info["brand"] is None


def test_get_full_status_handles_nonexistent_device():
    """Test that getFullStatus() returns None for non-existent device."""
    client = EmeraldHWS("test@example.com", "password")
    client._is_connected = True
    client.properties = MOCK_PROPERTY_RESPONSE_SELF["info"]["property"]

    # Query non-existent device
    status = client.getFullStatus("nonexistent-id")

    # Should return None, not crash
    assert status is None


def test_update_hws_state_handles_nonexistent_device():
    """Test that updateHWSState() gracefully handles non-existent device."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])

    # Store the original value before attempting update
    original_temp = client.properties[0]["heat_pump"][0]["last_state"]["temp_current"]

    # Update non-existent device - should not crash
    client.updateHWSState("nonexistent-id", "temp_current", 55)

    # Original device should be unchanged
    hws = client.properties[0]["heat_pump"][0]
    assert hws["last_state"]["temp_current"] == original_temp


@pytest.mark.parametrize("switch_value,expected", [
    (1, True),     # Numeric 1 should be on
    ("on", True),  # String "on" should be on
    (True, True),  # Boolean True == 1 in Python, so it matches
])
def test_switch_truthy_values_handled_correctly(switch_value, expected):
    """Test that truthy switch values are handled correctly."""
    client = EmeraldHWS("test@example.com", "password")
    client._is_connected = True
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])

    hws_id = "hws-1111-aaaa-2222-bbbb"

    client.properties[0]["heat_pump"][0]["last_state"]["switch"] = switch_value
    assert client.isOn(hws_id) is expected


@pytest.mark.parametrize("switch_value", [0, "off", False, None])
def test_switch_falsy_values_handled_correctly(switch_value):
    """Test that falsy switch values are correctly treated as off."""
    client = EmeraldHWS("test@example.com", "password")
    client._is_connected = True
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])

    hws_id = "hws-1111-aaaa-2222-bbbb"

    client.properties[0]["heat_pump"][0]["last_state"]["switch"] = switch_value
    assert client.isOn(hws_id) is False
