"""Tests for thread-safe state management."""

import copy
from emerald_hws import EmeraldHWS
from .conftest import (
    MOCK_PROPERTY_RESPONSE_SELF,
    MQTT_MSG_TEMP_UPDATE,
    MQTT_MSG_SWITCH_OFF,
    MQTT_MSG_WORK_STATE_HEATING,
)


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


def test_concurrent_energy_method_access():
    """Test that energy methods are thread-safe during concurrent access."""
    import threading

    client = EmeraldHWS("test@example.com", "password")
    client.properties = MOCK_PROPERTY_RESPONSE_SELF["info"]["property"]
    client._is_connected = True

    hws_id = "hws-1111-aaaa-2222-bbbb"

    results = {"daily": [], "weekly": [], "monthly": [], "historical": []}
    errors = []

    def read_daily_energy():
        try:
            for _ in range(10):
                result = client.getDailyEnergyUsage(hws_id)
                results["daily"].append(result)
        except Exception as e:
            errors.append(f"daily: {e}")

    def read_weekly_energy():
        try:
            for _ in range(10):
                result = client.getWeeklyEnergyUsage(hws_id)
                results["weekly"].append(result)
        except Exception as e:
            errors.append(f"weekly: {e}")

    def read_monthly_energy():
        try:
            for _ in range(10):
                result = client.getMonthlyEnergyUsage(hws_id)
                results["monthly"].append(result)
        except Exception as e:
            errors.append(f"monthly: {e}")

    def read_historical_consumption():
        try:
            for _ in range(10):
                result = client.getHistoricalConsumption(hws_id)
                results["historical"].append(result)
        except Exception as e:
            errors.append(f"historical: {e}")

    # Start concurrent read operations
    threads = [
        threading.Thread(target=read_daily_energy),
        threading.Thread(target=read_weekly_energy),
        threading.Thread(target=read_monthly_energy),
        threading.Thread(target=read_historical_consumption),
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    # Verify no errors occurred
    assert len(errors) == 0, f"Thread safety errors: {errors}"

    # Verify all methods returned consistent results
    assert len(results["daily"]) == 10
    assert len(results["weekly"]) == 10
    assert len(results["monthly"]) == 10
    assert len(results["historical"]) == 10

    # Verify results are consistent (all calls should return same data)
    assert all(r == results["daily"][0] for r in results["daily"])
    assert all(r == results["weekly"][0] for r in results["weekly"])
    assert all(r == results["monthly"][0] for r in results["monthly"])
    assert all(r == results["historical"][0] for r in results["historical"])


def test_concurrent_energy_updates_and_reads():
    """Test thread safety when updating consumption data while reading."""
    import threading

    client = EmeraldHWS("test@example.com", "password")
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client._is_connected = True

    hws_id = "hws-1111-aaaa-2222-bbbb"
    topic = f"ep/heat_pump/from_gw/{hws_id}"

    read_results = []
    errors = []

    def continuous_reads():
        try:
            for _ in range(20):
                daily = client.getDailyEnergyUsage(hws_id)
                weekly = client.getWeeklyEnergyUsage(hws_id)
                monthly = client.getMonthlyEnergyUsage(hws_id)
                historical = client.getHistoricalConsumption(hws_id)
                read_results.append((daily, weekly, monthly, historical))
        except Exception as e:
            errors.append(f"read_error: {e}")

    def energy_updates():
        try:
            # Process multiple energy updates with consistent dates
            for i in range(5):
                energy_msg = f'[{{"msg_id": "msg{i}", "namespace": "business", "command": "update_hour_energy", "direction": "gw2app", "property_id": "prop-aaaa-1111-bbbb-2222", "device_id": "{hws_id}"}}, {{"start_time": "2099-12-31 {i:02d}:00", "end_time": "2099-12-31 {i + 1:02d}:00", "data": {0.5 + i * 0.1}}}]'
                client.mqttDecodeUpdate(topic, energy_msg.encode())
        except Exception as e:
            errors.append(f"update_error: {e}")

    # Start concurrent operations
    read_thread = threading.Thread(target=continuous_reads)
    update_thread = threading.Thread(target=energy_updates)

    read_thread.start()
    update_thread.start()

    read_thread.join()
    update_thread.join()

    # Verify no errors occurred
    assert len(errors) == 0, f"Concurrent access errors: {errors}"

    # Verify reads were successful
    assert len(read_results) > 0

    # Verify final state is consistent
    final_historical = client.getHistoricalConsumption(hws_id)
    assert final_historical is not None
    assert "past_seven_days" in final_historical


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


def test_concurrent_heat_pump_state_updates():
    """Test concurrent state updates to different heat pumps using threads."""
    import threading
    from copy import deepcopy

    client = EmeraldHWS("test@example.com", "password")
    # Create a property with two heat pumps
    property_data = deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"][0])
    hws1 = property_data["heat_pump"][0]
    hws2 = deepcopy(hws1)
    hws2["id"] = "hws-2222-bbbb-3333-cccc"
    property_data["heat_pump"].append(hws2)
    client.properties = [property_data]

    def update_hws1():
        client.updateHWSState("hws-1111-aaaa-2222-bbbb", "temp_current", 70)

    def update_hws2():
        client.updateHWSState("hws-2222-bbbb-3333-cccc", "temp_current", 80)

    thread1 = threading.Thread(target=update_hws1)
    thread2 = threading.Thread(target=update_hws2)
    thread1.start()
    thread2.start()
    thread1.join()
    thread2.join()
    # Verify states are isolated and correct after concurrent updates
    assert client.properties[0]["heat_pump"][0]["last_state"]["temp_current"] == 70
    assert client.properties[0]["heat_pump"][1]["last_state"]["temp_current"] == 80


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
    client.mqttDecodeUpdate(
        f"ep/heat_pump/from_gw/{hws_id}", MQTT_MSG_WORK_STATE_HEATING
    )

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
    client.mqttDecodeUpdate(
        f"ep/heat_pump/from_gw/{hws_id}", MQTT_MSG_WORK_STATE_HEATING
    )

    # Verify callback invoked for each update
    assert len(callback_log) == 3

    # Verify all state changes were applied
    hws = client.properties[0]["heat_pump"][0]
    assert hws["last_state"]["temp_current"] == 59
    assert hws["last_state"]["switch"] == 0
    assert hws["last_state"]["work_state"] == 1


def test_replace_callback_functionality():
    """Test that replaceCallback properly replaces the update callback."""
    original_calls = []
    new_calls = []

    def original_callback():
        original_calls.append("original")

    def new_callback():
        new_calls.append("new")

    # Start with original callback
    client = EmeraldHWS(
        "test@example.com", "password", update_callback=original_callback
    )
    client.properties = MOCK_PROPERTY_RESPONSE_SELF["info"]["property"]

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # Trigger state update - original callback should be called
    client.updateHWSState(hws_id, "temp_current", 50)
    assert len(original_calls) == 1
    assert len(new_calls) == 0

    # Replace callback
    client.replaceCallback(new_callback)

    # Trigger state update - new callback should be called
    client.updateHWSState(hws_id, "temp_current", 55)
    assert len(original_calls) == 1  # Should not have changed
    assert len(new_calls) == 1

    # Verify only new callback continues to be called
    client.updateHWSState(hws_id, "temp_current", 60)
    assert len(original_calls) == 1  # Still unchanged
    assert len(new_calls) == 2

    # Test replacing with None (removing callback)
    client.replaceCallback(None)
    client.updateHWSState(hws_id, "temp_current", 65)
    assert len(original_calls) == 1  # Still unchanged
    assert len(new_calls) == 2  # Still unchanged
