"""Tests for query operations (status checks, energy usage, etc)."""
import copy
import json
import pytest
from unittest.mock import Mock
from emerald_hws import EmeraldHWS
from .conftest import (
    MOCK_LOGIN_RESPONSE,
    MOCK_PROPERTY_RESPONSE_SELF,
    MOCK_PROPERTY_RESPONSE_MIXED,
)


def test_get_full_status(mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mock_connection_event, mocker):
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
    mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mock_connection_event, mocker
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
    client.properties = MOCK_PROPERTY_RESPONSE_SELF["info"]["property"]
    client._is_connected = True

    # Set switch to 1
    client.properties[0]["heat_pump"][0]["last_state"]["switch"] = 1

    hws_id = "hws-1111-aaaa-2222-bbbb"
    assert client.isOn(hws_id) is True


def test_is_on_with_string_switch():
    """Test isOn() with switch='on' (string)."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = MOCK_PROPERTY_RESPONSE_SELF["info"]["property"]
    client._is_connected = True

    # Set switch to 'on'
    client.properties[0]["heat_pump"][0]["last_state"]["switch"] = "on"

    hws_id = "hws-1111-aaaa-2222-bbbb"
    assert client.isOn(hws_id) is True


def test_is_on_when_off():
    """Test isOn() returns False when switch=0."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = MOCK_PROPERTY_RESPONSE_SELF["info"]["property"]
    client._is_connected = True

    # Set switch to 0
    client.properties[0]["heat_pump"][0]["last_state"]["switch"] = 0

    hws_id = "hws-1111-aaaa-2222-bbbb"
    assert client.isOn(hws_id) is False


def test_is_heating_with_work_state():
    """Test isHeating() with work_state=1 (actively heating)."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = MOCK_PROPERTY_RESPONSE_SELF["info"]["property"]
    client._is_connected = True

    # Set work_state to 1 (heating)
    client.properties[0]["heat_pump"][0]["last_state"]["work_state"] = 1

    hws_id = "hws-1111-aaaa-2222-bbbb"
    assert client.isHeating(hws_id) is True


def test_is_heating_with_work_state_idle():
    """Test isHeating() with work_state=0 (idle/off)."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = MOCK_PROPERTY_RESPONSE_SELF["info"]["property"]
    client._is_connected = True

    # Set work_state to 0 (idle)
    client.properties[0]["heat_pump"][0]["last_state"]["work_state"] = 0

    hws_id = "hws-1111-aaaa-2222-bbbb"
    assert client.isHeating(hws_id) is False


def test_is_heating_with_work_state_on_not_heating():
    """Test isHeating() with work_state=2 (on but not heating)."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = MOCK_PROPERTY_RESPONSE_SELF["info"]["property"]
    client._is_connected = True

    # Set work_state to 2 (on but not heating)
    client.properties[0]["heat_pump"][0]["last_state"]["work_state"] = 2

    hws_id = "hws-1111-aaaa-2222-bbbb"
    assert client.isHeating(hws_id) is False


def test_is_heating_fallback_to_device_operation_status():
    """Test isHeating() falls back to device_operation_status when work_state not available."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = MOCK_PROPERTY_RESPONSE_SELF["info"]["property"]
    client._is_connected = True

    # Remove work_state to test fallback
    if "work_state" in client.properties[0]["heat_pump"][0]["last_state"]:
        del client.properties[0]["heat_pump"][0]["last_state"]["work_state"]

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
    client.properties = MOCK_PROPERTY_RESPONSE_SELF["info"]["property"]
    client._is_connected = True

    hws_id = "hws-1111-aaaa-2222-bbbb"
    result = client.getHourlyEnergyUsage(hws_id)

    # Should return tuple of (current_hour, last_data_at)
    assert result is not None
    current_hour, last_data_at = result
    assert current_hour == 0.96
    assert last_data_at == "2025-10-12 13:00"


def test_get_hourly_energy_usage_no_data():
    """Test getHourlyEnergyUsage returns None when no consumption data."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client._is_connected = True

    # Remove consumption_data
    client.properties[0]["heat_pump"][0]["consumption_data"] = None

    hws_id = "hws-1111-aaaa-2222-bbbb"
    result = client.getHourlyEnergyUsage(hws_id)

    assert result is None


def test_current_mode():
    """Test retrieving current mode (0=boost, 1=normal, 2=quiet)."""
    client = EmeraldHWS("test@example.com", "password")
    client.properties = MOCK_PROPERTY_RESPONSE_SELF["info"]["property"]
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
    client.properties = MOCK_PROPERTY_RESPONSE_SELF["info"]["property"]
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
    client.properties = MOCK_PROPERTY_RESPONSE_SELF["info"]["property"]
    client._is_connected = True

    info = client.getInfo("nonexistent-id")
    assert info is None


def test_list_hws(mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mock_connection_event, mocker):
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


def test_list_hws_multiple(mock_requests, mock_boto3, mock_mqtt5_client_builder, mock_auth, mock_io, mock_connection_event, mocker):
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


