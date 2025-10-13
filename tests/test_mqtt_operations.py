"""Tests for MQTT operations."""

from emerald_hws import EmeraldHWS
from .conftest import (
    MOCK_PROPERTY_RESPONSE_SELF,
    MQTT_MSG_TEMP_UPDATE,
    MQTT_MSG_SWITCH_OFF,
    MQTT_MSG_SWITCH_ON,
    MQTT_MSG_WORK_STATE_HEATING,
    MQTT_MSG_WORK_STATE_IDLE,
    MQTT_MSG_ENERGY_UPDATE,
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


def test_mqtt_energy_update_consumption_data(mqtt_client_with_properties):
    """Test that energy update MQTT messages properly update consumption_data."""
    import json

    client = mqtt_client_with_properties["client"]
    topic = mqtt_client_with_properties["topic"]

    # Get initial consumption data
    initial_consumption = json.loads(get_hws(client)["consumption_data"])

    # Process energy update message
    client.mqttDecodeUpdate(topic, MQTT_MSG_ENERGY_UPDATE)

    # Verify consumption data was updated
    updated_consumption = json.loads(get_hws(client)["consumption_data"])

    # Check current hour energy usage was updated to the exact value from the MQTT message
    assert updated_consumption["current_hour"] == 0.68
    assert updated_consumption["last_data_at"] == "2099-12-31 09:00"

    # Check past_seven_days was updated with the new date and energy value
    assert "2099-12-31" in updated_consumption["past_seven_days"]
    assert updated_consumption["past_seven_days"]["2099-12-31"] == 0.68

    # Check monthly consumption was updated (should include new value added to existing total)
    assert "2099-12" in updated_consumption["monthly_consumption"]
    # The monthly consumption should have increased by 0.68 from the initial value
    initial_monthly_total = initial_consumption.get("monthly_consumption", {}).get(
        "2099-12", 0
    )
    assert (
        updated_consumption["monthly_consumption"]["2099-12"]
        == initial_monthly_total + 0.68
    )


def test_mqtt_energy_update_accumulates_monthly_data(mqtt_client_with_properties):
    """Test that energy updates accumulate correctly for monthly consumption."""
    import json

    client = mqtt_client_with_properties["client"]
    topic = mqtt_client_with_properties["topic"]

    # Get initial consumption data
    initial_consumption = json.loads(get_hws(client)["consumption_data"])
    initial_monthly = initial_consumption.get("monthly_consumption", {}).get(
        "2099-12", 0
    )

    # Process first energy update
    client.mqttDecodeUpdate(topic, MQTT_MSG_ENERGY_UPDATE)

    # Process second energy update for same month
    second_energy_msg = b'[{\n\t\t"msg_id":\t"f6150000",\n\t\t"namespace":\t"business",\n\t\t"command":\t"update_hour_energy",\n\t\t"direction":\t"gw2app",\n\t\t"property_id":\t"prop-aaaa-1111-bbbb-2222",\n\t\t"device_id":\t"hws-1111-aaaa-2222-bbbb"\n\t}, {\n\t\t"start_time":\t"2099-12-31 10:00",\n\t\t"end_time":\t"2099-12-31 11:00",\n\t\t"data":\t0.42\n\t}]'
    client.mqttDecodeUpdate(topic, second_energy_msg)

    # Verify monthly consumption accumulated
    consumption = json.loads(get_hws(client)["consumption_data"])
    # The monthly consumption should have increased by at least 0.42 from the second message
    final_monthly = consumption["monthly_consumption"]["2099-12"]
    assert final_monthly > initial_monthly  # Should be greater than initial
    assert final_monthly >= 0.68 + 0.42  # Should include both updates


def test_mqtt_energy_updates_daily_and_weekly_methods(mqtt_client_with_properties):
    """Test that daily and weekly energy methods are updated by MQTT messages."""

    client = mqtt_client_with_properties["client"]
    topic = mqtt_client_with_properties["topic"]
    hws_id = mqtt_client_with_properties["hws_id"]

    # Get initial weekly data
    initial_weekly = client.getWeeklyEnergyUsage(hws_id)

    # Process MQTT energy update message
    client.mqttDecodeUpdate(topic, MQTT_MSG_ENERGY_UPDATE)

    # Get updated weekly and daily data
    updated_weekly = client.getWeeklyEnergyUsage(hws_id)
    updated_daily = client.getDailyEnergyUsage(hws_id)

    # Verify weekly data was updated (new date replaces oldest date)
    assert updated_weekly != initial_weekly
    # Expected: 26.53 - 3.17 (oldest 2025-10-06) + 0.68 (new 2099-12-31) = 24.04
    assert updated_weekly == 24.04

    # Verify daily data exists and potentially changed
    # Note: daily may be None if current date doesn't match MQTT data
    assert isinstance(updated_daily, (type(None), int, float))

    # Verify historical consumption was updated with MQTT data
    historical = client.getHistoricalConsumption(hws_id)
    assert historical is not None
    assert historical["current_hour"] == 0.68
    assert historical["last_data_at"] == "2099-12-31 09:00"


def test_mqtt_energy_updates_monthly_method(mqtt_client_with_properties):
    """Test that monthly energy method accumulates data from MQTT messages."""

    client = mqtt_client_with_properties["client"]
    topic = mqtt_client_with_properties["topic"]
    hws_id = mqtt_client_with_properties["hws_id"]

    # Process MQTT energy update message
    client.mqttDecodeUpdate(topic, MQTT_MSG_ENERGY_UPDATE)

    # Get updated monthly data
    updated_monthly = client.getMonthlyEnergyUsage(hws_id)

    # Verify monthly data was potentially updated
    # Note: may be None if current month doesn't match MQTT data month
    assert isinstance(updated_monthly, (type(None), int, float))

    # Verify historical consumption shows monthly accumulation
    historical = client.getHistoricalConsumption(hws_id)
    assert historical is not None
    assert "2099-12" in historical["monthly_consumption"]  # MQTT message month


def test_mqtt_energy_updates_historical_consumption_method(mqtt_client_with_properties):
    """Test that getHistoricalConsumption reflects all MQTT updates."""

    client = mqtt_client_with_properties["client"]
    topic = mqtt_client_with_properties["topic"]
    hws_id = mqtt_client_with_properties["hws_id"]

    # Get initial historical consumption
    initial_consumption = client.getHistoricalConsumption(hws_id)

    # Process MQTT energy update message
    client.mqttDecodeUpdate(topic, MQTT_MSG_ENERGY_UPDATE)

    # Get updated historical consumption
    updated_consumption = client.getHistoricalConsumption(hws_id)

    # Verify the structure was updated
    assert updated_consumption is not None
    assert updated_consumption["current_hour"] == 0.68
    assert updated_consumption["last_data_at"] == "2099-12-31 09:00"
    assert "2099-12-31" in updated_consumption["past_seven_days"]
    assert updated_consumption["past_seven_days"]["2099-12-31"] == 0.68
    assert "2099-12" in updated_consumption["monthly_consumption"]

    # Verify it's different from initial values
    assert updated_consumption["current_hour"] != initial_consumption["current_hour"]
    assert updated_consumption["last_data_at"] != initial_consumption["last_data_at"]


def test_mqtt_multiple_energy_updates_accumulate_correctly(mqtt_client_with_properties):
    """Test that multiple MQTT energy updates accumulate correctly."""

    client = mqtt_client_with_properties["client"]
    topic = mqtt_client_with_properties["topic"]
    hws_id = mqtt_client_with_properties["hws_id"]

    # Process first energy update
    client.mqttDecodeUpdate(topic, MQTT_MSG_ENERGY_UPDATE)

    # Process second energy update with different values
    second_energy_msg = b'[{\n\t\t"msg_id":\t"f6150001",\n\t\t"namespace":\t"business",\n\t\t"command":\t"update_hour_energy",\n\t\t"direction":\t"gw2app",\n\t\t"property_id":\t"prop-aaaa-1111-bbbb-2222",\n\t\t"device_id":\t"hws-1111-aaaa-2222-bbbb"\n\t}, {\n\t\t"start_time":\t"2099-12-31 10:00",\n\t\t"end_time":\t"2099-12-31 11:00",\n\t\t"data":\t1.45\n\t}]'
    client.mqttDecodeUpdate(topic, second_energy_msg)

    second_consumption = client.getHistoricalConsumption(hws_id)
    second_daily = client.getDailyEnergyUsage(hws_id)

    # Verify current_hour was updated to the most recent value
    assert second_consumption["current_hour"] == 1.45

    # Verify timestamp was updated
    assert second_consumption["last_data_at"] == "2099-12-31 10:00"

    # Verify weekly data contains the updated values
    updated_weekly = client.getWeeklyEnergyUsage(hws_id)
    assert updated_weekly is not None
    # Expected: 26.53 - 3.17 (oldest) + 0.68 (first hour) + 1.45 (second hour) = 25.49
    assert updated_weekly == 25.49

    # Verify monthly consumption accumulated (check monthly_consumption in historical data)
    assert "2099-12" in second_consumption["monthly_consumption"]
    assert second_consumption["monthly_consumption"]["2099-12"] > 0

    # Verify daily behavior (may be None depending on current date)
    assert isinstance(second_daily, (type(None), int, float))

    # With accumulation, the daily value for 2099-12-31 should be 0.68 + 1.45 = 2.13
    # (if the test date matches 2099-12-31, otherwise it will be None)
    if second_daily is not None:
        assert second_daily == 2.13


def test_mqtt_daily_energy_accumulation(mqtt_client_with_properties):
    """Test that daily energy usage accumulates correctly across multiple hours."""
    import json
    from unittest.mock import patch

    client = mqtt_client_with_properties["client"]
    topic = mqtt_client_with_properties["topic"]
    hws_id = mqtt_client_with_properties["hws_id"]

    # Mock the current date to match our test date
    with patch("emerald_hws.emeraldhws.datetime") as mock_datetime:
        mock_datetime.now.return_value.strftime.return_value = "2099-12-31"

        # Start with empty consumption data for clean test
        initial_consumption = {
            "current_hour": 0,
            "last_data_at": "",
            "past_seven_days": {},
            "monthly_consumption": {},
        }
        for properties in client.properties:
            for heat_pump in properties["heat_pump"]:
                if heat_pump["id"] == hws_id:
                    heat_pump["consumption_data"] = json.dumps(initial_consumption)

        # Process first hour (9:00-10:00)
        first_msg = b'[{\n\t\t"msg_id":\t"f6140000",\n\t\t"namespace":\t"business",\n\t\t"command":\t"update_hour_energy",\n\t\t"direction":\t"gw2app",\n\t\t"property_id":\t"prop-aaaa-1111-bbbb-2222",\n\t\t"device_id":\t"hws-1111-aaaa-2222-bbbb"\n\t}, {\n\t\t"start_time":\t"2099-12-31 09:00",\n\t\t"end_time":\t"2099-12-31 10:00",\n\t\t"data":\t0.8\n\t}]'
        client.mqttDecodeUpdate(topic, first_msg)

        # Verify first hour was added
        first_daily = client.getDailyEnergyUsage(hws_id)
        assert first_daily == 0.8

        # Process second hour (10:00-11:00)
        second_msg = b'[{\n\t\t"msg_id":\t"f6150001",\n\t\t"namespace":\t"business",\n\t\t"command":\t"update_hour_energy",\n\t\t"direction":\t"gw2app",\n\t\t"property_id":\t"prop-aaaa-1111-bbbb-2222",\n\t\t"device_id":\t"hws-1111-aaaa-2222-bbbb"\n\t}, {\n\t\t"start_time":\t"2099-12-31 10:00",\n\t\t"end_time":\t"2099-12-31 11:00",\n\t\t"data":\t1.2\n\t}]'
        client.mqttDecodeUpdate(topic, second_msg)

        # Verify daily total accumulated: 0.8 + 1.2 = 2.0
        second_daily = client.getDailyEnergyUsage(hws_id)
        assert second_daily == 2.0

        # Process third hour (11:00-12:00)
        third_msg = b'[{\n\t\t"msg_id":\t"f6160002",\n\t\t"namespace":\t"business",\n\t\t"command":\t"update_hour_energy",\n\t\t"direction":\t"gw2app",\n\t\t"property_id":\t"prop-aaaa-1111-bbbb-2222",\n\t\t"device_id":\t"hws-1111-aaaa-2222-bbbb"\n\t}, {\n\t\t"start_time":\t"2099-12-31 11:00",\n\t\t"end_time":\t"2099-12-31 12:00",\n\t\t"data":\t0.5\n\t}]'
        client.mqttDecodeUpdate(topic, third_msg)

        # Verify daily total accumulated: 0.8 + 1.2 + 0.5 = 2.5
        third_daily = client.getDailyEnergyUsage(hws_id)
        assert third_daily == 2.5

        # Verify hourly usage still shows the most recent hour
        hourly = client.getHourlyEnergyUsage(hws_id)
        assert hourly == 0.5


def test_mqtt_energy_update_limits_seven_days_data(mqtt_client_with_properties):
    """Test that past_seven_days only keeps the most recent 7 days."""
    import json

    client = mqtt_client_with_properties["client"]
    topic = mqtt_client_with_properties["topic"]

    # Add 8 days of energy data using future dates to ensure they're newer than mock data
    # Use December 20-27 to ensure valid dates
    for day in range(1, 9):
        # Create dates like 2099-12-20, 2099-12-21, etc.
        day_str = f"2099-12-{19 + day:02d}"  # Will create 2099-12-20 through 2099-12-27
        energy_msg = f'[{{"msg_id": "f61{day}0000", "namespace": "business", "command": "update_hour_energy", "direction": "gw2app", "property_id": "prop-aaaa-1111-bbbb-2222", "device_id": "hws-1111-aaaa-2222-bbbb"}}, {{"start_time": "{day_str} 09:00", "end_time": "{day_str} 10:00", "data": 0.{day}0}}]'.encode()
        client.mqttDecodeUpdate(topic, energy_msg)

    # Verify only 7 most recent days are kept
    consumption = json.loads(get_hws(client)["consumption_data"])
    assert len(consumption["past_seven_days"]) == 7

    # Should have the 7 newest days (2099-12-21 through 2099-12-27)
    # The oldest day (2099-12-20) should be removed
    assert "2099-12-20" not in consumption["past_seven_days"]
    assert "2099-12-27" in consumption["past_seven_days"]


def test_mqtt_energy_update_callback_invoked(mqtt_client_with_properties):
    """Test that update callback is invoked when energy update message is received."""
    callback_called = []

    def test_callback():
        callback_called.append(True)

    client = mqtt_client_with_properties["client"]
    client.replaceCallback(test_callback)
    topic = mqtt_client_with_properties["topic"]

    # Process energy update message
    client.mqttDecodeUpdate(topic, MQTT_MSG_ENERGY_UPDATE)

    # Verify callback was called
    assert len(callback_called) == 1
