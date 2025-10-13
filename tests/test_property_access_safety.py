"""Tests for safe property access and edge cases.

These tests ensure the module handles API changes gracefully, such as:
- Missing or None values in expected fields
- Type variations (switch can be 1, "on", or 0)
- Empty or malformed data structures

These are regression tests to prevent crashes when the API returns unexpected data.
"""

import pytest


def test_is_on_handles_missing_last_state(safety_test_client):
    """Test that isOn() handles missing last_state gracefully."""
    safety_test_client["hws"]["last_state"] = None

    # Should return False, not crash
    assert safety_test_client["client"].isOn(safety_test_client["hws_id"]) is False


def test_is_on_handles_missing_switch_key(safety_test_client):
    """Test that isOn() handles missing 'switch' key in last_state."""
    del safety_test_client["hws"]["last_state"]["switch"]

    # Should return False, not crash
    assert safety_test_client["client"].isOn(safety_test_client["hws_id"]) is False


def test_is_on_handles_numeric_switch(safety_test_client):
    """Test that isOn() correctly handles switch=1 (numeric)."""
    hws = safety_test_client["hws"]
    client = safety_test_client["client"]
    hws_id = safety_test_client["hws_id"]

    # Test with numeric 1
    hws["last_state"]["switch"] = 1
    assert client.isOn(hws_id) is True

    # Test with numeric 0
    hws["last_state"]["switch"] = 0
    assert client.isOn(hws_id) is False


def test_is_on_handles_string_switch(safety_test_client):
    """Test that isOn() correctly handles switch="on" (string)."""
    hws = safety_test_client["hws"]
    client = safety_test_client["client"]
    hws_id = safety_test_client["hws_id"]

    # Test with string "on"
    hws["last_state"]["switch"] = "on"
    assert client.isOn(hws_id) is True

    # Test with string "off"
    hws["last_state"]["switch"] = "off"
    assert client.isOn(hws_id) is False


def test_is_heating_handles_missing_work_state(safety_test_client):
    """Test that isHeating() falls back to device_operation_status when work_state missing."""
    hws = safety_test_client["hws"]
    client = safety_test_client["client"]
    hws_id = safety_test_client["hws_id"]

    # Remove work_state to test fallback
    hws["last_state"].pop("work_state", None)

    # Set device_operation_status to heating
    hws["device_operation_status"] = 1
    assert client.isHeating(hws_id) is True

    # Set device_operation_status to not heating
    hws["device_operation_status"] = 2
    assert client.isHeating(hws_id) is False


def test_is_heating_handles_no_status_fields(safety_test_client):
    """Test that isHeating() handles missing both work_state and device_operation_status."""
    hws = safety_test_client["hws"]

    # Remove work_state
    hws["last_state"].pop("work_state", None)

    # Remove device_operation_status
    hws.pop("device_operation_status", None)

    # Should return False, not crash
    assert safety_test_client["client"].isHeating(safety_test_client["hws_id"]) is False


def test_current_mode_handles_missing_mode(safety_test_client):
    """Test that currentMode() handles missing mode gracefully."""
    del safety_test_client["hws"]["last_state"]["mode"]

    # Should return None, not crash
    assert (
        safety_test_client["client"].currentMode(safety_test_client["hws_id"]) is None
    )


def test_get_hourly_energy_usage_handles_none_consumption_data(safety_test_client):
    """Test that getHourlyEnergyUsage() handles None consumption_data."""
    safety_test_client["hws"]["consumption_data"] = None

    # Should return None, not crash
    assert (
        safety_test_client["client"].getHourlyEnergyUsage(safety_test_client["hws_id"])
        is None
    )


def test_get_hourly_energy_usage_handles_malformed_json(safety_test_client):
    """Test that getHourlyEnergyUsage() handles malformed JSON in consumption_data."""
    import json as json_module

    # Set consumption_data to invalid JSON string
    safety_test_client["hws"]["consumption_data"] = "not valid json"

    # Should raise a JSONDecodeError
    with pytest.raises(json_module.JSONDecodeError):
        safety_test_client["client"].getHourlyEnergyUsage(safety_test_client["hws_id"])


def test_get_hourly_energy_usage_handles_missing_fields(safety_test_client):
    """Test that getHourlyEnergyUsage() handles missing current_hour or last_data_at."""
    import json

    # Set consumption_data with missing fields
    incomplete_data = {"past_seven_days": {}}
    safety_test_client["hws"]["consumption_data"] = json.dumps(incomplete_data)

    # Should return None, not crash
    assert (
        safety_test_client["client"].getHourlyEnergyUsage(safety_test_client["hws_id"])
        is None
    )


def test_get_info_handles_missing_fields(safety_test_client):
    """Test that getInfo() handles devices with missing optional fields."""
    hws = safety_test_client["hws"]
    hws_id = safety_test_client["hws_id"]

    # Remove some fields
    del hws["serial_number"]
    del hws["brand"]

    # Should still return dict with None values, not crash
    info = safety_test_client["client"].getInfo(hws_id)
    assert info is not None
    assert info["id"] == hws_id
    assert info["serial_number"] is None
    assert info["brand"] is None


def test_get_full_status_handles_nonexistent_device(safety_test_client):
    """Test that getFullStatus() returns None for non-existent device."""
    # Query non-existent device
    status = safety_test_client["client"].getFullStatus("nonexistent-id")

    # Should return None, not crash
    assert status is None


def test_update_hws_state_handles_nonexistent_device(safety_test_client):
    """Test that updateHWSState() gracefully handles non-existent device."""
    hws = safety_test_client["hws"]

    # Store the original value before attempting update
    original_temp = hws["last_state"]["temp_current"]

    # Update non-existent device - should not crash
    safety_test_client["client"].updateHWSState("nonexistent-id", "temp_current", 55)

    # Original device should be unchanged
    assert hws["last_state"]["temp_current"] == original_temp


@pytest.mark.parametrize(
    "switch_value,expected",
    [
        (1, True),  # Numeric 1 should be on
        ("on", True),  # String "on" should be on
        (True, True),  # Boolean True == 1 in Python, so it matches
    ],
)
def test_switch_truthy_values_handled_correctly(
    safety_test_client, switch_value, expected
):
    """Test that truthy switch values are handled correctly."""
    safety_test_client["hws"]["last_state"]["switch"] = switch_value
    assert safety_test_client["client"].isOn(safety_test_client["hws_id"]) is expected


@pytest.mark.parametrize("switch_value", [0, "off", False, None])
def test_switch_falsy_values_handled_correctly(safety_test_client, switch_value):
    """Test that falsy switch values are correctly treated as off."""
    safety_test_client["hws"]["last_state"]["switch"] = switch_value
    assert safety_test_client["client"].isOn(safety_test_client["hws_id"]) is False
