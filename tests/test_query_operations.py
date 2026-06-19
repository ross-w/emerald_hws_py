"""Tests for query operations (status checks, energy usage, etc)."""

import copy
import json
import pytest
from datetime import datetime
from unittest.mock import Mock, patch
from emerald_hws import EmeraldHWS
from .conftest import (
    MOCK_LOGIN_RESPONSE,
    MOCK_PROPERTY_RESPONSE_SELF,
    MOCK_PROPERTY_RESPONSE_MIXED,
    MQTT_MSG_ENERGY_UPDATE,
)


def test_get_full_status(
    mock_requests,
    mock_boto3,
    mock_mqtt5_client_builder,
    mock_auth,
    mock_io,
    mock_connection_event,
    mocker,
):
    """Test retrieving full status of a heat pump."""
    # Setup mocks
    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE
    mock_requests.post.return_value = mock_login

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_SELF
    mock_requests.get.return_value = mock_properties

    # Execute
    client = EmeraldHWS("test@example.com", "password")

    # Patch the connection event to avoid timeout
    mocker.patch.object(client._connection_event, "wait", return_value=True)

    client.connect()

    hws_id = "hws-1111-aaaa-2222-bbbb"
    status = client.getFullStatus(hws_id)

    # Assertions
    assert status is not None
    assert status["id"] == hws_id
    assert status["serial_number"] == "TEST1234567890"
    assert status["brand"] == "Emerald"
    assert "last_state" in status


def test_get_full_status_nonexistent_hws(
    mock_requests,
    mock_boto3,
    mock_mqtt5_client_builder,
    mock_auth,
    mock_io,
    mock_connection_event,
    mocker,
):
    """Test retrieving status for non-existent heat pump returns None."""
    # Setup mocks
    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE
    mock_requests.post.return_value = mock_login

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_SELF
    mock_requests.get.return_value = mock_properties

    # Execute
    client = EmeraldHWS("test@example.com", "password")

    # Patch the connection event to avoid timeout
    mocker.patch.object(client._connection_event, "wait", return_value=True)

    client.connect()

    status = client.getFullStatus("nonexistent-id")

    # Should return None
    assert status is None


def test_is_on_with_numeric_switch():
    """Test isOn() with switch=1 (numeric)."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client._is_connected = True

    # Set switch to 1
    client.properties[0]["heat_pump"][0]["last_state"]["switch"] = 1

    hws_id = "hws-1111-aaaa-2222-bbbb"
    assert client.isOn(hws_id) is True


def test_is_on_with_string_switch():
    """Test isOn() with switch='on' (string)."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client._is_connected = True

    # Set switch to 'on'
    client.properties[0]["heat_pump"][0]["last_state"]["switch"] = "on"

    hws_id = "hws-1111-aaaa-2222-bbbb"
    assert client.isOn(hws_id) is True


def test_is_on_when_off():
    """Test isOn() returns False when switch=0."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client._is_connected = True

    # Set switch to 0
    client.properties[0]["heat_pump"][0]["last_state"]["switch"] = 0

    hws_id = "hws-1111-aaaa-2222-bbbb"
    assert client.isOn(hws_id) is False


def test_is_heating_with_work_state():
    """Test isHeating() with work_state=1 (actively heating)."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client._is_connected = True

    # Set work_state to 1 (heating)
    client.properties[0]["heat_pump"][0]["last_state"]["work_state"] = 1

    hws_id = "hws-1111-aaaa-2222-bbbb"
    assert client.isHeating(hws_id) is True


def test_is_heating_with_work_state_idle():
    """Test isHeating() with work_state=0 (idle/off)."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client._is_connected = True

    # Set work_state to 0 (idle)
    client.properties[0]["heat_pump"][0]["last_state"]["work_state"] = 0

    hws_id = "hws-1111-aaaa-2222-bbbb"
    assert client.isHeating(hws_id) is False


def test_is_heating_with_work_state_on_not_heating():
    """Test isHeating() with work_state=2 (on but not heating)."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client._is_connected = True

    # Set work_state to 2 (on but not heating)
    client.properties[0]["heat_pump"][0]["last_state"]["work_state"] = 2

    hws_id = "hws-1111-aaaa-2222-bbbb"
    assert client.isHeating(hws_id) is False


def test_is_heating_fallback_to_device_operation_status():
    """Test isHeating() falls back to device_operation_status when work_state not available."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client._is_connected = True

    # Remove work_state to test fallback
    client.properties[0]["heat_pump"][0]["last_state"].pop("work_state", None)

    # Set device_operation_status to 1 (heating)
    client.properties[0]["heat_pump"][0]["device_operation_status"] = 1

    hws_id = "hws-1111-aaaa-2222-bbbb"
    assert client.isHeating(hws_id) is True

    # Test with device_operation_status = 2 (not heating)
    client.properties[0]["heat_pump"][0]["device_operation_status"] = 2
    assert client.isHeating(hws_id) is False


def test_get_hourly_energy_usage():
    """Test retrieving hourly energy usage."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client._is_connected = True

    hws_id = "hws-1111-aaaa-2222-bbbb"
    result = client.getHourlyEnergyUsage(hws_id)

    # Should return single energy value
    assert result is not None
    assert result == 0.96


def test_current_mode():
    """Test retrieving current mode (0=boost, 1=normal, 2=quiet)."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client._is_connected = True

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # Test normal mode
    client.properties[0]["heat_pump"][0]["last_state"]["mode"] = 1
    assert client.currentMode(hws_id) == 1

    # Test boost mode
    client.properties[0]["heat_pump"][0]["last_state"]["mode"] = 0
    assert client.currentMode(hws_id) == 0

    # Test quiet mode
    client.properties[0]["heat_pump"][0]["last_state"]["mode"] = 2
    assert client.currentMode(hws_id) == 2


def test_get_info():
    """Test retrieving identifying information for a heat pump."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client._is_connected = True

    hws_id = "hws-1111-aaaa-2222-bbbb"
    info = client.getInfo(hws_id)

    assert info is not None
    assert info["id"] == hws_id
    assert info["serial_number"] == "TEST1234567890"
    assert info["brand"] == "Emerald"
    assert info["hw_version"] == "V1.0.0"
    assert info["soft_version"] == "V1.0.34"


def test_get_info_nonexistent_hws():
    """Test getInfo returns None for non-existent heat pump."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client._is_connected = True

    info = client.getInfo("nonexistent-id")
    assert info is None


def test_list_hws(
    mock_requests,
    mock_boto3,
    mock_mqtt5_client_builder,
    mock_auth,
    mock_io,
    mock_connection_event,
    mocker,
):
    """Test listing all heat pump IDs."""
    # Setup mocks
    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE
    mock_requests.post.return_value = mock_login

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_SELF
    mock_requests.get.return_value = mock_properties

    # Execute
    client = EmeraldHWS("test@example.com", "password")

    # Patch the connection event to avoid timeout
    mocker.patch.object(client._connection_event, "wait", return_value=True)

    client.connect()

    hws_list = client.listHWS()

    # Assertions
    assert len(hws_list) == 1
    assert "hws-1111-aaaa-2222-bbbb" in hws_list


def test_list_hws_multiple(
    mock_requests,
    mock_boto3,
    mock_mqtt5_client_builder,
    mock_auth,
    mock_io,
    mock_connection_event,
    mocker,
):
    """Test listing multiple heat pumps from mixed properties."""
    # Setup mocks
    mock_login = Mock()
    mock_login.json.return_value = MOCK_LOGIN_RESPONSE
    mock_requests.post.return_value = mock_login

    mock_properties = Mock()
    mock_properties.json.return_value = MOCK_PROPERTY_RESPONSE_MIXED
    mock_requests.get.return_value = mock_properties

    # Execute
    client = EmeraldHWS("test@example.com", "password")

    # Patch the connection event to avoid timeout
    mocker.patch.object(client._connection_event, "wait", return_value=True)

    client.connect()

    hws_list = client.listHWS()

    # Should have both heat pumps
    assert len(hws_list) == 2
    assert "hws-1111-aaaa-2222-bbbb" in hws_list
    assert "hws-9999-eeee-8888-ffff" in hws_list


def test_get_hourly_energy_usage_returns_updated_values():
    """Test that getHourlyEnergyUsage returns updated values after MQTT message processing."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client._is_connected = True

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # Get initial energy usage
    initial_result = client.getHourlyEnergyUsage(hws_id)

    # Process MQTT energy update message
    topic = f"ep/heat_pump/from_gw/{hws_id}"
    client.mqttDecodeUpdate(topic, MQTT_MSG_ENERGY_UPDATE)

    # Get updated energy usage
    updated_result = client.getHourlyEnergyUsage(hws_id)

    # Verify values were updated
    assert updated_result == 0.68

    # Verify it's different from initial values
    assert updated_result != initial_result


def test_get_hourly_energy_usage_with_multiple_updates():
    """Test that getHourlyEnergyUsage reflects the most recent MQTT update."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client._is_connected = True

    hws_id = "hws-1111-aaaa-2222-bbbb"
    topic = f"ep/heat_pump/from_gw/{hws_id}"

    # Process first energy update
    client.mqttDecodeUpdate(topic, MQTT_MSG_ENERGY_UPDATE)
    first_result = client.getHourlyEnergyUsage(hws_id)

    # Process second energy update with different values
    second_energy_msg = b'[{\n\t\t"msg_id":\t"f6150000",\n\t\t"namespace":\t"business",\n\t\t"command":\t"update_hour_energy",\n\t\t"direction":\t"gw2app",\n\t\t"property_id":\t"prop-aaaa-1111-bbbb-2222",\n\t\t"device_id":\t"hws-1111-aaaa-2222-bbbb"\n\t}, {\n\t\t"start_time":\t"2099-12-31 10:00",\n\t\t"end_time":\t"2099-12-31 11:00",\n\t\t"data":\t1.23\n\t}]'
    client.mqttDecodeUpdate(topic, second_energy_msg)
    second_result = client.getHourlyEnergyUsage(hws_id)

    # Verify the method returns the most recent values
    assert second_result == 1.23
    assert second_result != first_result


def test_get_daily_energy_usage():
    """Test retrieving daily energy usage returns appropriate value."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client._is_connected = True

    hws_id = "hws-1111-aaaa-2222-bbbb"
    result = client.getDailyEnergyUsage(hws_id)

    # Should return either a numeric value (if today's date is in past_seven_days)
    # or None (if today's date not found in mock data)
    assert result is None or isinstance(result, (int, float))
    if result is not None:
        assert result >= 0  # Energy usage should be non-negative


def test_get_daily_energy_usage_missing_date_in_data():
    """Test getDailyEnergyUsage handles case where current date not in past_seven_days."""
    client = EmeraldHWS("test@example.com", "password")

    # Create custom consumption data without today's date (using dates far in the past)
    custom_consumption = json.dumps(
        {
            "current_hour": 1.5,
            "last_data_at": "2025-10-15 14:00",
            "past_seven_days": {
                "2024-01-01": 2.1,  # Far past dates to ensure they don't match today
                "2024-01-02": 1.8,
            },
            "monthly_consumption": {"2025-10": 15.5},
        }
    )

    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client.properties[0]["heat_pump"][0]["consumption_data"] = custom_consumption
    client._is_connected = True

    hws_id = "hws-1111-aaaa-2222-bbbb"
    result = client.getDailyEnergyUsage(hws_id)

    # Should return None when today's date not found in past_seven_days
    assert result is None


def test_get_weekly_energy_usage():
    """Test retrieving weekly energy usage structure."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client._is_connected = True

    hws_id = "hws-1111-aaaa-2222-bbbb"
    result = client.getWeeklyEnergyUsage(hws_id)

    # Should return total energy for past 7 days
    assert result is not None
    assert isinstance(result, (int, float))

    # Expected total: 3.17 + 4.14 + 3.86 + 4.73 + 2.69 + 4.08 + 3.86 = 26.53
    assert result == 26.53


def test_get_monthly_energy_usage():
    """Test retrieving monthly energy usage returns numeric value when data exists."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client._is_connected = True

    hws_id = "hws-1111-aaaa-2222-bbbb"
    result = client.getMonthlyEnergyUsage(hws_id)

    # Should return a numeric value (float or int) when data exists
    # Note: May return None if current month not in mock data
    assert result is None or isinstance(result, (int, float))
    if result is not None:
        assert result >= 0  # Energy usage should be non-negative


def test_get_monthly_energy_usage_missing_month_in_data():
    """Test getMonthlyEnergyUsage handles case where current month not in monthly_consumption."""
    client = EmeraldHWS("test@example.com", "password")

    # Create custom consumption data without current month
    custom_consumption = json.dumps(
        {
            "current_hour": 1.5,
            "last_data_at": "2025-10-15 14:00",
            "past_seven_days": {"2025-10-15": 2.1},
            "monthly_consumption": {
                "2025-09": 45.2,  # Previous month only
                "2025-08": 38.7,
            },
        }
    )

    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client.properties[0]["heat_pump"][0]["consumption_data"] = custom_consumption
    client._is_connected = True

    hws_id = "hws-1111-aaaa-2222-bbbb"
    result = client.getMonthlyEnergyUsage(hws_id)

    # Should return None when current month not found in monthly_consumption
    assert result is None


def test_get_historical_consumption():
    """Test retrieving full historical consumption data structure."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client._is_connected = True

    hws_id = "hws-1111-aaaa-2222-bbbb"
    result = client.getHistoricalConsumption(hws_id)

    # Should return the complete consumption data structure
    assert result is not None
    assert isinstance(result, dict)

    # Check all expected fields are present
    assert "current_hour" in result
    assert "last_data_at" in result
    assert "past_seven_days" in result
    assert "monthly_consumption" in result

    # Verify values match mock data
    assert result["current_hour"] == 0.96
    assert result["last_data_at"] == "2025-10-12 13:00"
    assert len(result["past_seven_days"]) == 7
    assert "2025-10-12" in result["past_seven_days"]
    assert "2025-10" in result["monthly_consumption"]


def test_get_daily_energy_usage_handles_invalid_data_gracefully():
    """Test that getDailyEnergyUsage handles edge cases gracefully without datetime dependency."""
    client = EmeraldHWS("test@example.com", "password")

    # Test with empty past_seven_days - should return None for any current date
    custom_consumption = json.dumps(
        {
            "current_hour": 1.2,
            "last_data_at": "2023-12-31 14:00",
            "past_seven_days": {},  # Empty - guaranteed not to contain today's date
            "monthly_consumption": {"2023-12": 45.2},
        }
    )

    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client.properties[0]["heat_pump"][0]["consumption_data"] = custom_consumption
    client._is_connected = True

    hws_id = "hws-1111-aaaa-2222-bbbb"
    result = client.getDailyEnergyUsage(hws_id)

    # Should return None since past_seven_days is empty
    assert result is None


def test_get_monthly_energy_usage_handles_missing_month():
    """Test that getMonthlyEnergyUsage returns None when current month not in data."""
    client = EmeraldHWS("test@example.com", "password")

    # Create custom consumption data without current month (using only old months)
    custom_consumption = json.dumps(
        {
            "current_hour": 1.2,
            "last_data_at": "2023-12-31 14:00",
            "past_seven_days": {
                "2023-12-25": 2.5,
                "2023-12-26": 1.8,
            },
            "monthly_consumption": {
                "2023-01": 45.2,  # January 2023 - won't match current month
                "2023-12": 38.7,  # December 2023 - won't match current month
            },
        }
    )

    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client.properties[0]["heat_pump"][0]["consumption_data"] = custom_consumption
    client._is_connected = True

    hws_id = "hws-1111-aaaa-2222-bbbb"
    result = client.getMonthlyEnergyUsage(hws_id)

    # Should return None since current month (e.g., 2025-10) won't be in 2023 data
    assert result is None


def test_energy_methods_handle_edge_cases_gracefully():
    """Test that energy methods handle edge cases without crashing."""
    client = EmeraldHWS("test@example.com", "password")

    # Test with completely empty consumption data - should return None gracefully
    custom_consumption = json.dumps(
        {
            "current_hour": 0,
            "last_data_at": "",
            "past_seven_days": {},
            "monthly_consumption": {},
        }
    )

    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client.properties[0]["heat_pump"][0]["consumption_data"] = custom_consumption
    client._is_connected = True

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # All methods should handle empty data gracefully
    daily_result = client.getDailyEnergyUsage(hws_id)
    weekly_result = client.getWeeklyEnergyUsage(hws_id)
    monthly_result = client.getMonthlyEnergyUsage(hws_id)

    assert daily_result is None
    assert weekly_result == 0  # Empty dict should sum to 0
    assert monthly_result is None


def test_energy_methods_handle_various_date_formats_in_data():
    """Test that energy methods handle different date formats in past_seven_days data."""
    client = EmeraldHWS("test@example.com", "password")

    # Create custom consumption data with various date formats
    custom_consumption = json.dumps(
        {
            "current_hour": 1.5,
            "last_data_at": "2025-10-15 14:00",
            "past_seven_days": {
                "2025-10-15": 2.1,  # Standard format
                "2025-10-8": 1.8,  # Single digit day
                "2025-9-30": 2.5,  # Single digit month
            },
            "monthly_consumption": {
                "2025-10": 25.5,
                "2025-9": 18.2,  # Single digit month
                "2025-12": 30.1,
            },
        }
    )

    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client.properties[0]["heat_pump"][0]["consumption_data"] = custom_consumption
    client._is_connected = True

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # Test weekly consumption handles various date formats
    weekly = client.getWeeklyEnergyUsage(hws_id)
    assert weekly is not None
    assert isinstance(weekly, (int, float))

    # Expected total: 2.1 + 1.8 + 2.5 = 6.4
    assert weekly == 6.4

    # Test monthly consumption handles various month formats
    monthly = client.getMonthlyEnergyUsage(hws_id)
    # This will return None unless current month matches one of the test months
    assert monthly is None or isinstance(monthly, (int, float))

    # Test historical consumption returns all data intact
    historical = client.getHistoricalConsumption(hws_id)
    assert historical is not None
    assert len(historical["past_seven_days"]) == 3
    assert len(historical["monthly_consumption"]) == 3


def test_get_daily_energy_usage_day_boundary_scenario():
    """Test getDailyEnergyUsage when current day not yet in past_seven_days data."""
    client = EmeraldHWS("test@example.com", "password")

    # Create consumption data without today's date (simulating before Emerald updates)
    custom_consumption = json.dumps(
        {
            "current_hour": 0.96,
            "last_data_at": "2025-10-14 23:00",  # Last update was yesterday
            "past_seven_days": {
                "2025-10-14": 4.2,  # Yesterday's data
                "2025-10-13": 3.8,
                "2025-10-12": 4.1,
            },
            "monthly_consumption": {"2025-10": 45.6},
        }
    )

    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client.properties[0]["heat_pump"][0]["consumption_data"] = custom_consumption
    client._is_connected = True

    hws_id = "hws-1111-aaaa-2222-bbbb"

    # Mock datetime to return a date not in the data
    with patch("emerald_hws.emeraldhws.datetime") as mock_datetime:
        mock_datetime.now.return_value.strftime.return_value = "2025-10-15"

        # Should return None since today (2025-10-15) not in past_seven_days yet
        result = client.getDailyEnergyUsage(hws_id)
        assert result is None

    # Verify other methods still work
    weekly = client.getWeeklyEnergyUsage(hws_id)
    assert weekly == 4.2 + 3.8 + 4.1  # Should sum existing data


# --- consumption_data parsing edge cases (no energy history) ---

HWS_ID = "hws-1111-aaaa-2222-bbbb"


def _make_client(consumption_data, omit=False):
    """Builds a connected client with the heat pump's consumption_data set
    to the given value (or removed entirely when omit is True)."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    heat_pump = client.properties[0]["heat_pump"][0]
    if omit:
        heat_pump.pop("consumption_data", None)
    else:
        heat_pump["consumption_data"] = consumption_data
    client._is_connected = True
    return client


# (label, value, omit) — the "no data" shapes _parseConsumption must tolerate
NO_DATA_CASES = [
    ("none", None, False),  # API returns key present but null (the bug)
    ("empty_json", "{}", False),  # empty JSON object
    ("missing", None, True),  # key absent entirely
    ("not_json", "not-json", False),  # malformed, non-JSON string
    ("bad_json", "{bad}", False),  # syntactically invalid JSON
    ("empty_string", "", False),  # empty string payload
    ("json_null", "null", False),  # valid JSON but not an object
]


@pytest.mark.parametrize("label,value,omit", NO_DATA_CASES)
def test_energy_getters_no_data(label, value, omit):
    """All energy getters treat null/empty/missing consumption_data as no data
    rather than raising."""
    client = _make_client(value, omit=omit)

    assert client.getHourlyEnergyUsage(HWS_ID) is None
    assert client.getDailyEnergyUsage(HWS_ID) is None
    assert client.getWeeklyEnergyUsage(HWS_ID) == 0
    assert client.getMonthlyEnergyUsage(HWS_ID) is None
    assert client.getHistoricalConsumption(HWS_ID) == {}


def test_malformed_nested_consumption_data_normalization():
    """Nested containers that aren't dicts are normalized to {} so the getters
    don't crash on a malformed-but-valid-JSON payload."""
    malformed = json.dumps(
        {
            "current_hour": 0.5,
            "past_seven_days": ["not", "a", "dict"],
            "monthly_consumption": "also-not-a-dict",
        }
    )
    client = _make_client(malformed)

    assert client.getHourlyEnergyUsage(HWS_ID) == 0.5  # scalar untouched
    assert client.getWeeklyEnergyUsage(HWS_ID) == 0  # list -> {} -> sum() == 0
    assert client.getMonthlyEnergyUsage(HWS_ID) is None  # str -> {} -> no month
    historical = client.getHistoricalConsumption(HWS_ID)
    assert historical["past_seven_days"] == {}
    assert historical["monthly_consumption"] == {}


def test_energy_getters_populated_payload():
    """A normal populated consumption_data still parses correctly (happy path)."""
    # Fixed dates so the test stays deterministic across day/month boundaries
    today = "2099-12-31"
    current_month = "2099-12"
    payload = {
        "current_hour": 0.42,
        "last_data_at": f"{today} 09:00",
        "past_seven_days": {today: 1.5},
        "monthly_consumption": {current_month: 12.3},
    }
    client = _make_client(json.dumps(payload))

    with patch("emerald_hws.emeraldhws.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2099, 12, 31)

        assert client.getHourlyEnergyUsage(HWS_ID) == 0.42
        assert client.getDailyEnergyUsage(HWS_ID) == 1.5
        assert client.getWeeklyEnergyUsage(HWS_ID) == 1.5
        assert client.getMonthlyEnergyUsage(HWS_ID) == 12.3
        assert client.getHistoricalConsumption(HWS_ID) == payload


@pytest.mark.parametrize(
    "consumption_data,omit",
    [
        (None, False),
        ("not-json", False),
        ("null", False),
        ("", False),
        (None, True),  # key entirely absent
    ],
)
def test_update_energy_usage_with_no_prior_data(consumption_data, omit):
    """The MQTT update path builds the default structure (rather than raising)
    when consumption_data is null/malformed/non-object/absent, and records the new hour."""
    client = _make_client(consumption_data, omit=omit)

    topic = f"ep/heat_pump/from_gw/{HWS_ID}"
    client.mqttDecodeUpdate(topic, MQTT_MSG_ENERGY_UPDATE)

    assert client.getHourlyEnergyUsage(HWS_ID) == 0.68
    historical = client.getHistoricalConsumption(HWS_ID)
    assert historical["past_seven_days"]["2099-12-31"] == 0.68
    assert historical["monthly_consumption"]["2099-12"] == 0.68


def test_update_energy_usage_preserves_existing_history():
    """The MQTT update path merges non-destructively: prior days/months are kept,
    while the new hour accumulates into the matching day and month."""
    # MQTT_MSG_ENERGY_UPDATE reports 0.68 kWh for start_time 2099-12-31 09:00
    existing = {
        "current_hour": 1.0,
        "last_data_at": "2099-12-30 10:00",
        "past_seven_days": {"2099-12-30": 2.0, "2099-12-31": 0.32},
        "monthly_consumption": {"2099-11": 50.0, "2099-12": 5.0},
    }
    client = _make_client(json.dumps(existing))

    topic = f"ep/heat_pump/from_gw/{HWS_ID}"
    client.mqttDecodeUpdate(topic, MQTT_MSG_ENERGY_UPDATE)

    assert client.getHourlyEnergyUsage(HWS_ID) == 0.68
    historical = client.getHistoricalConsumption(HWS_ID)

    # Prior day untouched; same day accumulates the new hour
    assert historical["past_seven_days"]["2099-12-30"] == 2.0
    assert historical["past_seven_days"]["2099-12-31"] == pytest.approx(0.32 + 0.68)

    # Prior month untouched; current month accumulates the new hour
    assert historical["monthly_consumption"]["2099-11"] == 50.0
    assert historical["monthly_consumption"]["2099-12"] == pytest.approx(5.0 + 0.68)
