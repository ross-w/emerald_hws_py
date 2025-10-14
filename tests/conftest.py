"""Shared fixtures and mock data for tests."""

import json
from unittest.mock import Mock
import pytest


# Anonymized mock data based on real API responses
MOCK_LOGIN_RESPONSE = {
    "code": 200,
    "message": "Login successful",
    "token": "mock_jwt_token_12345",
}

MOCK_LOGIN_FAILURE_RESPONSE = {"code": 401, "message": "Invalid credentials"}

# Property with heat pump in "property" array (Self-owned)
MOCK_PROPERTY_RESPONSE_SELF = {
    "code": 200,
    "message": "Property list",
    "info": {
        "property": [
            {
                "id": "prop-aaaa-1111-bbbb-2222",
                "customer_id": "cust-cccc-3333-dddd-4444",
                "property_name": "Test Home",
                "house_no": None,
                "unit_number": "2",
                "street_type": "Street",
                "street": "Test",
                "city": "Melbourne",
                "unit_type": "Unit",
                "level_type": None,
                "level_number": None,
                "street_number": "123",
                "street_suffix": None,
                "state": "VIC",
                "postal_code": "3000",
                "latitude": -37.8136,
                "longitude": 144.9631,
                "address_type": "residential",
                "premium": "No",
                "is_structure_deleted": 0,
                "accessibility": False,
                "is_structure_updated": 0,
                "created_at": "2024-01-12 12:26:14",
                "updated_at": "2024-10-09 22:29:03",
                "property_type": "Self",
                "tariff_structure": [],
                "member_count": 1,
                "property_spaces": None,
                "budget": None,
                "location": None,
                "devices": [],
                "livelinks": [],
                "safelinks": [],
                "heat_pump": [
                    {
                        "id": "hws-1111-aaaa-2222-bbbb",
                        "serial_number": "TEST1234567890",
                        "heat_pump_name": None,
                        "is_solar": True,
                        "is_solar_soaker_on": False,
                        "is_maintenance_required": 0,
                        "property_id": "prop-aaaa-1111-bbbb-2222",
                        "customer_id": "cust-cccc-3333-dddd-4444",
                        "space_id": None,
                        "installer_id": None,
                        "parent_agency_id": None,
                        "agency_id": None,
                        "agency_name": None,
                        "agent_name": "Installed by customer",
                        "installer_uuid": None,
                        "multi_site_company_id": None,
                        "site_id": None,
                        "consumption_data": json.dumps(
                            {
                                "current_hour": 0.96,
                                "last_data_at": "2025-10-12 13:00",
                                "past_seven_days": {
                                    "2025-10-06": 3.17,
                                    "2025-10-07": 4.14,
                                    "2025-10-08": 3.86,
                                    "2025-10-09": 4.73,
                                    "2025-10-10": 2.69,
                                    "2025-10-11": 4.08,
                                    "2025-10-12": 3.86,
                                },
                                "monthly_consumption": {
                                    "2024-10": 84.88,
                                    "2024-11": 96.94,
                                    "2024-12": 104.17,
                                    "2025-01": 87.26,
                                    "2025-02": 75.40,
                                    "2025-03": 98.09,
                                    "2025-04": 92.56,
                                    "2025-05": 130.03,
                                    "2025-06": 167.85,
                                    "2025-07": 175.18,
                                    "2025-08": 155.80,
                                    "2025-09": 130.81,
                                    "2025-10": 46.01,
                                },
                            }
                        ),
                        "customer_status": None,
                        "installed_by": "self",
                        "brand": "Emerald",
                        "model": "model",
                        "hw_version": "V1.0.0",
                        "soft_version": "V1.0.34",
                        "mac_address": "aabbccddeeff",
                        "wifi_name": "TestWiFi",
                        "ip_address": None,
                        "status": "active",
                        "connection_type": "Bluetooth",
                        "upgradable": 0,
                        "force_update": 0,
                        "available_firmware": "1.0.33",
                        "heat_pump_type": "type-5555-6666-7777-8888",
                        "radius": 200,
                        "latitude": None,
                        "longitude": None,
                        "installation_date": "2024-01-12",
                        "last_state": {
                            "mode": 1,
                            "switch": "on",
                            "temp_set": 60,
                            "temp_current": 60,
                        },
                        "heat_pump_installed_by": None,
                        "created_at": "2024-01-12 12:29:46",
                        "updated_at": "2024-10-25 21:54:26",
                        "fault_code": None,
                        "fault_description": None,
                        "last_fault_timestamp": None,
                        "fault_email_codes": None,
                        "is_online": 1,
                        "last_disconnect": None,
                        "is_disconnected_notification_sent": 0,
                        "signal_strength": "-60db",
                        "reconnect": 1,
                        "last_seen": "2025-10-12 14:29:38",
                        "device_operation_status": 2,
                        "is_lowtemp_notification_sent": 0,
                        "lowtemp_notification_timestamp": None,
                        "low_temp_notification_toggle": True,
                        "manual_intervention": None,
                        "manual_intervention_time": None,
                        "manual_intervention_notification": None,
                        "upgrade_steps": 0,
                        "is_qr": 0,
                        "series_type": "pro",
                        "set_time_date": "2025-10-12 04:57:16",
                        "device_type": "heat_pump",
                    }
                ],
            }
        ],
        "shared_property": [],
        "badge_count": 0,
        "homepage_slider": [],
    },
}

# Property with heat pump in "shared_property" array
MOCK_PROPERTY_RESPONSE_SHARED = {
    "code": 200,
    "message": "Property list",
    "info": {
        "property": [],
        "shared_property": [
            {
                "id": "prop-9999-eeee-8888-ffff",
                "customer_id": "cust-7777-gggg-6666-hhhh",
                "property_name": "Shared Home",
                "house_no": None,
                "unit_number": None,
                "street_type": "Avenue",
                "street": "Test",
                "city": "Sydney",
                "unit_type": "House",
                "level_type": None,
                "level_number": None,
                "street_number": "42",
                "street_suffix": None,
                "state": "NSW",
                "postal_code": "2000",
                "latitude": None,
                "longitude": None,
                "address_type": "residential",
                "premium": "No",
                "is_structure_deleted": 0,
                "accessibility": False,
                "is_structure_updated": 0,
                "created_at": "2025-08-20 15:34:57",
                "updated_at": "2025-08-20 15:34:57",
                "property_type": "Shared",
                "tariff_structure": [],
                "member_count": 2,
                "property_spaces": None,
                "budget": None,
                "location": None,
                "livelinks": [],
                "safelinks": [],
                "heat_pump": [
                    {
                        "id": "hws-9999-eeee-8888-ffff",
                        "serial_number": "TEST9876543210",
                        "heat_pump_name": None,
                        "is_solar": None,
                        "is_solar_soaker_on": False,
                        "is_maintenance_required": 0,
                        "property_id": "prop-9999-eeee-8888-ffff",
                        "customer_id": "cust-7777-gggg-6666-hhhh",
                        "space_id": None,
                        "installer_id": None,
                        "parent_agency_id": None,
                        "agency_id": None,
                        "agency_name": None,
                        "agent_name": "Installed by customer",
                        "installer_uuid": None,
                        "multi_site_company_id": None,
                        "site_id": None,
                        "consumption_data": json.dumps(
                            {
                                "current_hour": 0,
                                "last_data_at": "2025-10-12 07:00",
                                "past_seven_days": {
                                    "2025-10-10": 2.72,
                                    "2025-10-11": 2.29,
                                    "2025-10-12": 0,
                                },
                                "monthly_consumption": {"2025-10": 5.01},
                            }
                        ),
                        "customer_status": None,
                        "installed_by": "self",
                        "brand": "Emerald",
                        "model": "model",
                        "hw_version": "V1.0.0",
                        "soft_version": "V1.0.34",
                        "mac_address": "112233445566",
                        "wifi_name": "TestSharedWiFi",
                        "ip_address": None,
                        "status": "active",
                        "connection_type": "Bluetooth",
                        "upgradable": 0,
                        "force_update": 0,
                        "available_firmware": None,
                        "heat_pump_type": "type-aaaa-bbbb-cccc-dddd",
                        "radius": 200,
                        "latitude": None,
                        "longitude": None,
                        "installation_date": "2025-08-20",
                        "last_state": {
                            "mode": 1,
                            "switch": "on",
                            "temp_set": 60,
                            "temp_current": 56,
                        },
                        "heat_pump_installed_by": None,
                        "created_at": "2025-10-10 08:46:23",
                        "updated_at": "2025-10-10 08:47:16",
                        "fault_code": None,
                        "fault_description": None,
                        "last_fault_timestamp": None,
                        "fault_email_codes": None,
                        "is_online": 1,
                        "last_disconnect": None,
                        "is_disconnected_notification_sent": None,
                        "signal_strength": "-69db",
                        "reconnect": 1,
                        "last_seen": "2025-10-11 19:46:35",
                        "device_operation_status": 2,
                        "is_lowtemp_notification_sent": 0,
                        "lowtemp_notification_timestamp": None,
                        "low_temp_notification_toggle": True,
                        "manual_intervention": None,
                        "manual_intervention_time": None,
                        "manual_intervention_notification": None,
                        "upgrade_steps": 0,
                        "is_qr": 0,
                        "series_type": "pro",
                        "set_time_date": "2025-10-11 19:06:41",
                        "device_type": "heat_pump",
                    }
                ],
                "devices": [],
            }
        ],
        "badge_count": 0,
        "homepage_slider": [],
    },
}

# Mixed property response (both self and shared)
MOCK_PROPERTY_RESPONSE_MIXED = {
    "code": 200,
    "message": "Property list",
    "info": {
        "property": MOCK_PROPERTY_RESPONSE_SELF["info"]["property"],
        "shared_property": MOCK_PROPERTY_RESPONSE_SHARED["info"]["shared_property"],
        "badge_count": 0,
        "homepage_slider": [],
    },
}

# Empty property response
MOCK_PROPERTY_RESPONSE_EMPTY = {
    "code": 200,
    "message": "Property list",
    "info": {
        "property": [],
        "shared_property": [],
        "badge_count": 0,
        "homepage_slider": [],
    },
}

# AWS Cognito mock response
MOCK_COGNITO_IDENTITY = {
    "IdentityId": "ap-southeast-2:mock-identity-1111-2222-3333-4444"
}

# MQTT message examples
MQTT_MSG_TEMP_UPDATE = b'[{\n\t\t"msg_id":\t"27180000",\n\t\t"namespace":\t"business",\n\t\t"command":\t"upload_status",\n\t\t"direction":\t"gw2app",\n\t\t"property_id":\t"prop-aaaa-1111-bbbb-2222",\n\t\t"device_id":\t"hws-1111-aaaa-2222-bbbb"\n\t}, {\n\t\t"temp_current":\t59\n\t}]'

MQTT_MSG_SWITCH_OFF = b'[{\n\t\t"msg_id":\t"6b180000",\n\t\t"namespace":\t"business",\n\t\t"command":\t"upload_status",\n\t\t"direction":\t"gw2app",\n\t\t"property_id":\t"prop-aaaa-1111-bbbb-2222",\n\t\t"device_id":\t"hws-1111-aaaa-2222-bbbb"\n\t}, {\n\t\t"switch":\t0\n\t}]'

MQTT_MSG_SWITCH_ON = b'[{\n\t\t"msg_id":\t"6d180000",\n\t\t"namespace":\t"business",\n\t\t"command":\t"upload_status",\n\t\t"direction":\t"gw2app",\n\t\t"property_id":\t"prop-aaaa-1111-bbbb-2222",\n\t\t"device_id":\t"hws-1111-aaaa-2222-bbbb"\n\t}, {\n\t\t"switch":\t1\n\t}]'

MQTT_MSG_WORK_STATE_HEATING = b'[{\n\t\t"msg_id":\t"6e180000",\n\t\t"namespace":\t"business",\n\t\t"command":\t"upload_status",\n\t\t"direction":\t"gw2app",\n\t\t"property_id":\t"prop-aaaa-1111-bbbb-2222",\n\t\t"device_id":\t"hws-1111-aaaa-2222-bbbb"\n\t}, {\n\t\t"work_state":\t1\n\t}]'

MQTT_MSG_WORK_STATE_IDLE = b'[{\n\t\t"msg_id":\t"6c180000",\n\t\t"namespace":\t"business",\n\t\t"command":\t"upload_status",\n\t\t"direction":\t"gw2app",\n\t\t"property_id":\t"prop-aaaa-1111-bbbb-2222",\n\t\t"device_id":\t"hws-1111-aaaa-2222-bbbb"\n\t}, {\n\t\t"work_state":\t0\n\t}]'

MQTT_MSG_ENERGY_UPDATE = b'[{\n\t\t"msg_id":\t"f6140000",\n\t\t"namespace":\t"business",\n\t\t"command":\t"update_hour_energy",\n\t\t"direction":\t"gw2app",\n\t\t"property_id":\t"prop-aaaa-1111-bbbb-2222",\n\t\t"device_id":\t"hws-1111-aaaa-2222-bbbb"\n\t}, {\n\t\t"start_time":\t"2099-12-31 09:00",\n\t\t"end_time":\t"2099-12-31 10:00",\n\t\t"data":\t0.68,\n\t\t"temp_current_12":\t42,\n\t\t"temp_current_11":\t41,\n\t\t"temp_current_10":\t40,\n\t\t"temp_current_9":\t40,\n\t\t"temp_current_8":\t39,\n\t\t"temp_current_7":\t38,\n\t\t"temp_current_6":\t37,\n\t\t"temp_current_5":\t36,\n\t\t"temp_current_4":\t35,\n\t\t"temp_current_3":\t35,\n\t\t"temp_current_2":\t34,\n\t\t"temp_current_1":\t33,\n\t\t"power_consumption_6":\t0.10999999940395355,\n\t\t"power_consumption_5":\t0.119999997317791,\n\t\t"power_consumption_4":\t0.119999997317791,\n\t\t"power_consumption_3":\t0.10999999940395355,\n\t\t"power_consumption_2":\t0.10000000149011612,\n\t\t"power_consumption_1":\t0.119999997317791\n\t}]'

MQTT_MSG_CONTROL_RESPONSE_OK = b'[{\n\t\t"msg_id":\t"121",\n\t\t"namespace":\t"business",\n\t\t"command":\t"control",\n\t\t"direction":\t"gw2app",\n\t\t"property_id":\t"prop-aaaa-1111-bbbb-2222",\n\t\t"device_id":\t"hws-1111-aaaa-2222-bbbb"\n\t}, {\n\t\t"result":\t"ok",\n\t\t"switch":\t0\n\t}]'


def make_mqtt_update(device_id, property_id, **updates):
    """Factory for creating MQTT update messages.

    Args:
        device_id: Device UUID (e.g., "hws-1111-aaaa-2222-bbbb")
        property_id: Property UUID (e.g., "prop-aaaa-1111-bbbb-2222")
        **updates: Key-value pairs for the update payload (e.g., temp_current=59, switch=1)

    Returns:
        bytes: Encoded MQTT message in Emerald's expected format

    Example:
        >>> make_mqtt_update("hws-123", "prop-456", temp_current=59, switch=1)
        b'[{"msg_id":"...", "namespace":"business", ...}, {"temp_current":59, "switch":1}]'
    """
    import random

    msg = [
        {
            "msg_id": f"{random.randint(10000000, 99999999)}",
            "namespace": "business",
            "command": "upload_status",
            "direction": "gw2app",
            "property_id": property_id,
            "device_id": device_id,
        },
        updates,
    ]
    return json.dumps(msg).encode("utf-8")


@pytest.fixture
def mock_requests(mocker):
    """Mock requests library for API calls."""
    return mocker.patch("emerald_hws.emeraldhws.requests")


@pytest.fixture
def mock_boto3(mocker):
    """Mock boto3 for AWS Cognito."""
    mock_client = Mock()
    mock_client.get_id.return_value = MOCK_COGNITO_IDENTITY
    mock_boto3 = mocker.patch("emerald_hws.emeraldhws.boto3")
    mock_boto3.client.return_value = mock_client
    return mock_boto3


@pytest.fixture
def mock_mqtt5_client_builder(mocker):
    """Mock MQTT5 client builder."""
    mock_client = Mock()
    mock_client.start.return_value = None
    mock_client.stop.return_value = Mock(result=Mock(return_value=None))
    mock_client.subscribe.return_value = Mock(result=Mock(return_value=None))
    mock_client.publish.return_value = Mock(result=Mock(return_value=None))

    mock_builder = mocker.patch("emerald_hws.emeraldhws.mqtt5_client_builder")
    mock_builder.websockets_with_default_aws_signing.return_value = mock_client

    return mock_builder


@pytest.fixture
def mock_connection_event():
    """Placeholder fixture - not actually used anymore.

    Connection event patching is now done directly in tests via mocker.patch.object()
    """
    pass


@pytest.fixture
def mock_auth(mocker):
    """Mock AWS auth credentials provider."""
    mock_provider = Mock()
    mock_auth = mocker.patch("emerald_hws.emeraldhws.auth")
    mock_auth.AwsCredentialsProvider.new_cognito.return_value = mock_provider
    return mock_auth


@pytest.fixture
def mock_io(mocker):
    """Mock AWS IO TLS context."""
    return mocker.patch("emerald_hws.emeraldhws.io")


@pytest.fixture
def mqtt_client_with_properties():
    """Fixture providing a client with properties pre-configured for MQTT tests.

    Returns a dict with:
    - client: EmeraldHWS instance with properties set and connected flag
    - hws_id: Standard HWS ID for testing
    - topic: Standard MQTT topic for testing
    """
    from emerald_hws import EmeraldHWS
    import copy

    client = EmeraldHWS("test@example.com", "password")
    client.properties = copy.deepcopy(MOCK_PROPERTY_RESPONSE_SELF["info"]["property"])
    client._is_connected = True  # Set connected flag to bypass connection checks

    return {
        "client": client,
        "hws_id": "hws-1111-aaaa-2222-bbbb",
        "topic": "ep/heat_pump/from_gw/hws-1111-aaaa-2222-bbbb",
    }
