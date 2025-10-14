import json
import logging
import random
import threading
import time
from datetime import datetime

import boto3
import requests
from awscrt import mqtt5, auth, io
from awsiot import mqtt5_client_builder


class EmeraldHWS:
    """Implementation of the web API for Emerald Heat Pump Hot Water Systems"""

    COMMON_HEADERS = {
        "accept": "*/*",
        "content-type": "application/json",
        "user-agent": "EmeraldPlanet/2.5.3 (com.emerald-ems.customer; build:5; iOS 17.2.1) Alamofire/5.4.1",
        "accept-language": "en-GB;q=1.0, en-AU;q=0.9",
    }

    MQTT_HOST = "a13v32g67itvz9-ats.iot.ap-southeast-2.amazonaws.com"
    COGNITO_IDENTITY_POOL_ID = "ap-southeast-2:f5bbb02c-c00e-4f10-acb3-e7d1b05268e8"

    def __init__(
        self,
        email,
        password,
        update_callback=None,
        connection_timeout_minutes=720,
        health_check_minutes=60,
    ):
        """Initialise the API client
        :param email: The email address for logging into the Emerald app
        :param password: The password for the supplied user account
        :param update_callback: Optional callback function to be called when an update is available
        :param connection_timeout_minutes: Optional timeout in minutes before reconnecting MQTT (default: 720 minutes/12 hours)
        :param health_check_minutes: Optional interval in minutes to check for message activity (default: 60 minutes/1 hour)
        """

        self.email = email
        self.password = password
        self.token = ""
        self.properties = {}
        self.logger = logging.getLogger(__name__)
        self.update_callback = update_callback
        self._state_lock = threading.RLock()  # Thread-safe lock for state operations
        self._connection_event = (
            threading.Event()
        )  # Event to signal when MQTT connection is established
        self._connect_lock = (
            threading.Lock()
        )  # Lock to prevent concurrent connect() calls
        self._mqtt_lock = (
            threading.RLock()
        )  # Lock to protect MQTT client lifecycle operations
        self._is_connected = False  # Flag to track connection state
        self.mqttClient = None  # Initialise to None

        # Convert minutes to seconds for internal use
        self.connection_timeout = connection_timeout_minutes * 60.0
        self.health_check_interval = (
            health_check_minutes * 60.0 if health_check_minutes > 0 else 0
        )
        self.last_message_time = None
        self.health_check_timer = None
        self.reconnect_timer = None

        # Connection state tracking
        self.connection_state = "initial"  # possible states: initial, connected, failed
        self.consecutive_failures = 0
        self.max_backoff_seconds = 60  # Maximum backoff of 1 minute

        # Ensure reasonable minimum values (e.g., at least 5 minutes for connection timeout)
        if connection_timeout_minutes < 5 and connection_timeout_minutes != 0:
            self.logger.warning(
                "emeraldhws: Connection timeout too short, setting to minimum of 5 minutes"
            )
            self.connection_timeout = 5 * 60.0

        # Ensure reasonable minimum values for health check (e.g., at least 5 minutes)
        if 0 < health_check_minutes < 5:
            self.logger.warning(
                "emeraldhws: Health check interval too short, setting to minimum of 5 minutes"
            )
            self.health_check_interval = 5 * 60.0

    def getLoginToken(self):
        """Performs an API request to get a token from the API"""
        url = "https://api.emerald-ems.com.au/api/v1/customer/sign-in"

        payload = {
            "app_version": "2.5.3",
            "device_name": "iPhone15,2",
            "device_os_version": "17.2.1",
            "device_type": "iOS",
            "email": self.email,
            "password": self.password,
        }

        headers = self.COMMON_HEADERS

        post_response = requests.post(url, json=payload, headers=headers)

        post_response_json = post_response.json()
        if post_response_json.get("code") == 200:
            self.token = post_response_json.get("token")
            return True
        else:
            raise Exception("Failed to log into Emerald API with supplied credentials")

    def getAllHWS(self):
        """Interrogates the API to list out all hot water systems on the account"""

        if not self.token:
            self.getLoginToken()

        url = "https://api.emerald-ems.com.au/api/v1/customer/property/list"
        headers = self.COMMON_HEADERS
        headers["authorization"] = "Bearer {}".format(self.token)

        post_response = requests.get(url, headers=headers)
        post_response_json = post_response.json()

        if post_response_json.get("code") == 200:
            self.logger.debug("emeraldhws: Successfully logged into Emerald API")
            info = post_response_json.get("info", {})

            # Retrieve both property and shared_property arrays
            property_data = info.get("property", [])
            shared_property_data = info.get("shared_property", [])

            # Combine both arrays into a single list
            combined_properties = []
            if isinstance(property_data, list):
                combined_properties.extend(property_data)
            if isinstance(shared_property_data, list):
                combined_properties.extend(shared_property_data)

            with self._state_lock:
                self.properties = combined_properties

            # Check if we got valid data
            if len(combined_properties) == 0:
                # Log the full response when properties are invalid to help diagnose the issue
                self.logger.debug(
                    f"emeraldhws: Poperties empty/invalid, full response: {post_response_json}"
                )
                raise Exception(
                    "No heat pumps found on account - API returned empty or invalid property list"
                )
        else:
            raise Exception("Unable to fetch properties from Emerald API")

    def _wait_for_properties(self, timeout=30):
        """
        Wait for properties to be populated and return a thread-safe copy.
        Blocks until properties is a non-empty list or timeout occurs.

        :param timeout: Maximum seconds to wait
        :returns: List of properties
        :raises: Exception if timeout or properties not available
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            with self._state_lock:
                if isinstance(self.properties, list) and len(self.properties) > 0:
                    return list(self.properties)  # Return a copy
            time.sleep(0.1)  # Small delay before retry

        # Timeout - provide detailed error message
        with self._state_lock:
            final_value = self.properties
        raise Exception(
            f"Timeout waiting for properties to be populated. Current value: {type(final_value).__name__} = {final_value}"
        )

    def replaceCallback(self, update_callback):
        """Replaces the current registered update callback (if any) with the supplied"""

        self.update_callback = update_callback

    def reconnectMQTT(self, reason="scheduled"):
        """Stops an existing MQTT connection and creates a new one
        :param reason: Reason for reconnection (scheduled, health_check, etc.)
        """
        with self._mqtt_lock:
            self.logger.info(
                f"emeraldhws: awsiot: Reconnecting MQTT connection (reason: {reason})"
            )

            if self.mqttClient is not None:
                # Clear connection event before stopping
                self._connection_event.clear()

                try:
                    # Stop the client and wait for it to fully stop
                    stop_future = self.mqttClient.stop()
                    if stop_future:
                        # Wait up to 10 seconds for clean shutdown
                        stop_future.result(timeout=10)
                    self.logger.debug(
                        "emeraldhws: awsiot: MQTT client stopped successfully"
                    )
                except Exception as e:
                    self.logger.warning(
                        f"emeraldhws: awsiot: Error stopping MQTT client: {e}"
                    )
                finally:
                    # Always clear the client reference
                    self.mqttClient = None

            self.connectMQTT()
            self.subscribeAllHWS()

            self.logger.info(
                f"emeraldhws: awsiot: MQTT reconnection completed (reason: {reason})"
            )

    def connectMQTT(self):
        """Establishes a connection to Amazon IOT core's MQTT service"""
        with self._mqtt_lock:
            # If already connected, skip
            if self.mqttClient is not None:
                self.logger.debug(
                    "emeraldhws: awsiot: MQTT client already exists, skipping connection"
                )
                return

            # Clear the connection event before starting new connection
            self._connection_event.clear()

            # Certificate path is available but not currently used in the connection
            # os.path.join(os.path.dirname(__file__), '__assets__', 'SFSRootCAG2.pem')
            identityPoolID = self.COGNITO_IDENTITY_POOL_ID
            region = self.MQTT_HOST.split(".")[2]
            cognito_endpoint = "cognito-identity." + region + ".amazonaws.com"
            cognitoIdentityClient = boto3.client("cognito-identity", region_name=region)

            temporaryIdentityId = cognitoIdentityClient.get_id(
                IdentityPoolId=identityPoolID
            )
            identityID = temporaryIdentityId["IdentityId"]
            self.logger.debug(
                "emeraldhws: awsiot: AWS IoT IdentityID: {}".format(identityID)
            )

            credentials_provider = auth.AwsCredentialsProvider.new_cognito(
                endpoint=cognito_endpoint,
                identity=identityID,
                tls_ctx=io.ClientTlsContext(io.TlsContextOptions()),
            )

            client = mqtt5_client_builder.websockets_with_default_aws_signing(
                endpoint=self.MQTT_HOST,
                region=region,
                credentials_provider=credentials_provider,
                on_connection_interrupted=self.on_connection_interrupted,
                on_connection_resumed=self.on_connection_resumed,
                on_lifecycle_connection_success=self.on_lifecycle_connection_success,
                on_lifecycle_stopped=self.on_lifecycle_stopped,
                on_lifecycle_attempting_connect=self.on_lifecycle_attempting_connect,
                on_lifecycle_disconnection=self.on_lifecycle_disconnection,
                on_lifecycle_connection_failure=self.on_lifecycle_connection_failure,
                on_publish_received=self.mqttCallback,
                # The default keep-alive is 20 minutes, which we might want to reduce
                # keep_alive_interval_sec = 60,
            )

            client.start()
            self.mqttClient = client

            # Block until connection is established or timeout (30 seconds)
            if not self._connection_event.wait(timeout=30):
                self.logger.warning(
                    "emeraldhws: awsiot: Connection establishment timed out after 30 seconds"
                )
                # Continue anyway - the connection may still succeed asynchronously

    def mqttDecodeUpdate(self, topic, payload):
        """Attempt to decode a received MQTT message and direct appropriately
        :param topic: MQTT topic
        :param payload: MQTT payload
        """
        json_payload = json.loads(payload.decode("utf-8"))
        hws_id = topic.split("/")[-1]

        command = json_payload[0].get("command")
        if command is not None:
            if command == "upload_status":
                for key in json_payload[1]:
                    self.updateHWSState(hws_id, key, json_payload[1][key])
            elif command == "update_hour_energy":
                self._updateEnergyUsage(hws_id, json_payload[1])

    def mqttCallback(self, publish_packet_data):
        """Calls decode update for received message"""
        publish_packet = publish_packet_data.publish_packet
        assert isinstance(publish_packet, mqtt5.PublishPacket)
        self.logger.debug(
            "emeraldhws: awsiot: Received message from MQTT topic {}: {}".format(
                publish_packet.topic, publish_packet.payload
            )
        )
        self.last_message_time = time.time()  # Update the last message time
        self.mqttDecodeUpdate(publish_packet.topic, publish_packet.payload)

    def on_connection_interrupted(self, connection, error, **kwargs):
        """Log error when MQTT is interrupted"""
        error_code = getattr(error, "code", "unknown")
        error_name = getattr(error, "name", "unknown")
        self.logger.info(
            f"emeraldhws: awsiot: Connection interrupted. Error: {error_name} (code: {error_code}), Message: {error}"
        )

    def on_connection_resumed(self, connection, return_code, session_present, **kwargs):
        """Log message when MQTT is resumed"""
        self.logger.debug(
            "emeraldhws: awsiot: Connection resumed. return_code: {} session_present: {}".format(
                return_code, session_present
            )
        )

    def on_lifecycle_connection_success(
        self, lifecycle_connect_success_data: mqtt5.LifecycleConnectSuccessData
    ):
        """Log message when connection succeeded"""
        self.logger.debug("emeraldhws: awsiot: connection succeeded")
        # Reset failure counter and update connection state
        self.consecutive_failures = 0
        self.connection_state = "connected"
        # Signal that connection is established
        self._connection_event.set()
        return

    def on_lifecycle_connection_failure(
        self, lifecycle_connection_failure: mqtt5.LifecycleConnectFailureData
    ):
        """Log message when connection failed"""
        error = lifecycle_connection_failure.exception
        error_code = getattr(error, "code", "unknown")
        error_name = getattr(error, "name", "unknown")
        error_message = str(error)

        # Update connection state and increment failure counter
        self.connection_state = "failed"
        self.consecutive_failures += 1

        # Log at INFO level since this is important for troubleshooting
        self.logger.info(
            f"emeraldhws: awsiot: connection failed - Error: {error_name} (code: {error_code}), Message: {error_message}"
        )

        # Log additional error details if available
        if hasattr(error, "__dict__"):
            self.logger.debug(f"emeraldhws: awsiot: error details: {error.__dict__}")

        # If there's a CONNACK packet available, log its details too
        if (
            hasattr(lifecycle_connection_failure, "connack_packet")
            and lifecycle_connection_failure.connack_packet
        ):
            connack = lifecycle_connection_failure.connack_packet
            reason_code = getattr(connack, "reason_code", "unknown")
            reason_string = getattr(connack, "reason_string", "")
            if reason_string:
                self.logger.info(
                    f"emeraldhws: awsiot: MQTT CONNACK reason: {reason_code} - {reason_string}"
                )
            else:
                self.logger.info(
                    f"emeraldhws: awsiot: MQTT CONNACK reason code: {reason_code}"
                )

            # Log all CONNACK properties if available
            if hasattr(connack, "__dict__"):
                self.logger.debug(
                    f"emeraldhws: awsiot: CONNACK details: {connack.__dict__}"
                )

            if reason_code == mqtt5.ConnectReasonCode.CLIENT_IDENTIFIER_NOT_VALID:
                self.logger.debug(
                    "emeraldhws: awsiot: The client identifier is not valid. Getting a new login token."
                )
                self.getLoginToken()
                self.reconnectMQTT(reason="invalid_client_id")
        else:
            self.logger.debug(
                "emeraldhws: awsiot: no CONNACK packet available in failure data"
            )

        # Log the exception data structure itself for deeper debugging
        if hasattr(lifecycle_connection_failure, "__dict__"):
            self.logger.debug(
                f"emeraldhws: awsiot: failure data: {lifecycle_connection_failure.__dict__}"
            )

        return

    def on_lifecycle_stopped(self, lifecycle_stopped_data: mqtt5.LifecycleStoppedData):
        """Log message when stopped"""
        self.logger.debug("emeraldhws: awsiot: stopped")
        # Clear connection event when stopped
        self._connection_event.clear()
        return

    def on_lifecycle_disconnection(
        self, lifecycle_disconnect_data: mqtt5.LifecycleDisconnectData
    ):
        """Log message when disconnected"""
        # Extract disconnect reason if available
        reason = "unknown reason"
        if (
            hasattr(lifecycle_disconnect_data, "disconnect_packet")
            and lifecycle_disconnect_data.disconnect_packet
        ):
            disconnect_packet = lifecycle_disconnect_data.disconnect_packet
            reason_code = getattr(disconnect_packet, "reason_code", "unknown")
            reason_string = getattr(disconnect_packet, "reason_string", "")
            reason = f"reason code: {reason_code}" + (
                f" - {reason_string}" if reason_string else ""
            )

            # Log full disconnect packet details at debug level
            if hasattr(disconnect_packet, "__dict__"):
                self.logger.debug(
                    f"emeraldhws: awsiot: disconnect packet details: {disconnect_packet.__dict__}"
                )
        else:
            # Log the disconnect data structure if no packet available
            if hasattr(lifecycle_disconnect_data, "__dict__"):
                self.logger.debug(
                    f"emeraldhws: awsiot: disconnect data: {lifecycle_disconnect_data.__dict__}"
                )

        self.logger.info(f"emeraldhws: awsiot: disconnected - {reason}")

        # Clear connection event when disconnected
        self._connection_event.clear()
        self._is_connected = False
        return

    def on_lifecycle_attempting_connect(
        self, lifecycle_attempting_connect_data: mqtt5.LifecycleAttemptingConnectData
    ):
        """Log message when attempting connect"""
        self.logger.debug("emeraldhws: awsiot: attempting to connect")
        return

    def scheduled_reconnect(self):
        """Periodic MQTT reconnect - called by timer and reschedules itself"""
        self.reconnectMQTT(reason="scheduled")

        # Reschedule for next time
        if self.connection_timeout > 0:
            self.reconnect_timer = threading.Timer(
                self.connection_timeout, self.scheduled_reconnect
            )
            self.reconnect_timer.daemon = True
            self.reconnect_timer.start()

    def check_connection_health(self):
        """Check if we've received any messages recently, reconnect if not
        Called by timer and reschedules itself
        """
        if self.last_message_time is None:
            # No messages received yet, don't reconnect
            self.logger.debug(
                "emeraldhws: awsiot: Health check - No messages received yet"
            )
        else:
            current_time = time.time()
            time_since_last_message = current_time - self.last_message_time
            minutes_since_last = time_since_last_message / 60.0

            if time_since_last_message > self.health_check_interval:
                # This is an INFO level log because it's an important event
                self.logger.info(
                    f"emeraldhws: awsiot: No messages received for {minutes_since_last:.1f} minutes, reconnecting"
                )

                # If we're in a failed state, apply exponential backoff
                if self.connection_state == "failed" and self.consecutive_failures > 0:
                    # Calculate backoff time with exponential increase, capped at max_backoff_seconds
                    backoff_seconds = min(
                        2 ** (self.consecutive_failures - 1), self.max_backoff_seconds
                    )
                    self.logger.info(
                        f"emeraldhws: awsiot: Connection in failed state, applying backoff of {backoff_seconds} seconds before retry (attempt {self.consecutive_failures})"
                    )
                    time.sleep(backoff_seconds)

                self.reconnectMQTT(reason="health_check")
            else:
                # This is a DEBUG level log to avoid cluttering logs
                self.logger.debug(
                    f"emeraldhws: awsiot: Health check - Last message received {minutes_since_last:.1f} minutes ago"
                )

        # Always reschedule next health check
        if self.health_check_interval > 0:
            self.health_check_timer = threading.Timer(
                self.health_check_interval, self.check_connection_health
            )
            self.health_check_timer.daemon = True
            self.health_check_timer.start()

    def updateHWSState(self, id, key, value):
        """Updates the specified value for the supplied key in the HWS id specified
        :param id: ID of the HWS
        :param key: key to update (eg temp_current)
        :param value: value to set
        """

        with self._state_lock:
            for properties in self.properties:
                heat_pumps = properties.get("heat_pump", [])
                for heat_pump in heat_pumps:
                    if heat_pump["id"] == id:
                        heat_pump["last_state"][key] = value

        # Call callback AFTER releasing lock to avoid potential deadlocks
        if self.update_callback is not None:
            self.update_callback()

    def _updateEnergyUsage(self, id, energy_data):
        """Updates energy consumption data from MQTT update_hour_energy messages
        :param id: ID of the HWS
        :param energy_data: Energy data dictionary from MQTT message
        """
        start_time = energy_data["start_time"]
        current_hour_energy = energy_data["data"]
        date_key = start_time.split(" ")[0]  # Extract date part
        month_key = date_key[:7]  # Extract month part

        with self._state_lock:
            for properties in self.properties:
                for heat_pump in properties["heat_pump"]:
                    if heat_pump["id"] == id:
                        # Get or create consumption data
                        consumption = (
                            json.loads(heat_pump["consumption_data"])
                            if heat_pump.get("consumption_data")
                            else {
                                "current_hour": 0,
                                "last_data_at": "",
                                "past_seven_days": {},
                                "monthly_consumption": {},
                            }
                        )

                        # Update current hour and timestamp
                        consumption["current_hour"] = current_hour_energy
                        consumption["last_data_at"] = start_time
                        consumption["past_seven_days"][date_key] = (
                            consumption["past_seven_days"].get(date_key, 0)
                            + current_hour_energy
                        )

                        # Keep only last 7 days
                        if len(consumption["past_seven_days"]) > 7:
                            sorted_dates = sorted(consumption["past_seven_days"])
                            for old_date in sorted_dates[:-7]:
                                del consumption["past_seven_days"][old_date]

                        # Update monthly consumption
                        consumption["monthly_consumption"][month_key] = (
                            consumption["monthly_consumption"].get(month_key, 0)
                            + current_hour_energy
                        )

                        # Save back to heat pump
                        heat_pump["consumption_data"] = json.dumps(consumption)
                        break

        if self.update_callback:
            self.update_callback()

    def subscribeForUpdates(self, id):
        """Subscribes to the MQTT topics for the supplied HWS
        :param id: The UUID of the requested HWS
        """
        with self._mqtt_lock:
            retry = 0
            while not self.mqttClient:
                self.connectMQTT()
                if retry >= 3:
                    raise Exception("MQTT client not connected after multiple attempts")
                retry += 1

            mqtt_topic = "ep/heat_pump/from_gw/{}".format(id)
            subscribe_future = self.mqttClient.subscribe(
                subscribe_packet=mqtt5.SubscribePacket(
                    subscriptions=[
                        mqtt5.Subscription(
                            topic_filter=mqtt_topic, qos=mqtt5.QoS.AT_LEAST_ONCE
                        )
                    ]
                )
            )

            # Wait for subscription to complete
            subscribe_future.result(20)

    def getFullStatus(self, id):
        """Returns a dict with the full status of the specified HWS
        :param id: UUID of the HWS to get the status for
        """

        if not self._is_connected:
            self.connect()

        with self._state_lock:
            for properties in self.properties:
                heat_pumps = properties.get("heat_pump", [])
                for heat_pump in heat_pumps:
                    if heat_pump["id"] == id:
                        return heat_pump
        return None

    def sendControlMessage(self, id, payload):
        """Sends a message via MQTT to the HWS
        :param id: The UUID of the requested HWS
        :param payload: JSON payload to send eg {"switch":1}
        """

        if not self._is_connected:
            self.connect()

        hwsdetail = self.getFullStatus(id)
        if not hwsdetail:
            raise Exception(f"Unable to find HWS with ID {id}")

        msg = [
            {
                "device_id": id,
                "namespace": "business",
                "direction": "app2gw",
                "property_id": hwsdetail.get("property_id"),
                "command": "control",
                "hw_id": hwsdetail.get("mac_address"),
                "msg_id": "{}".format(random.randint(100, 9999)),
            },
            payload,
        ]
        mqtt_topic = "ep/heat_pump/to_gw/{}".format(id)

        with self._mqtt_lock:
            if not self.mqttClient:
                raise Exception("MQTT client not connected")
            publish_future = self.mqttClient.publish(
                mqtt5.PublishPacket(
                    topic=mqtt_topic,
                    payload=json.dumps(msg),
                    qos=mqtt5.QoS.AT_LEAST_ONCE,
                )
            )

        # Wait for publish to complete outside the lock
        publish_future.result(20)  # 20 seconds

    def turnOn(self, id):
        """Turns the specified HWS on
        :param id: The UUID of the HWS to turn on
        """
        self.logger.debug("emeraldhws: Sending control message: turn on")
        self.sendControlMessage(id, {"switch": 1})

    def turnOff(self, id):
        """Turns the specified HWS off
        :param id: The UUID of the HWS to turn off
        """
        self.logger.debug("emeraldhws: Sending control message: turn off")
        self.sendControlMessage(id, {"switch": 0})

    def setNormalMode(self, id):
        """Sets the specified HWS to normal (not Boost or Quiet) mode
        :param id: The UUID of the HWS to set to normal mode
        """
        self.logger.debug("emeraldhws: Sending control message: normal mode")
        self.sendControlMessage(id, {"mode": 1})

    def setBoostMode(self, id):
        """Sets the specified HWS to boost (high power) mode
        :param id: The UUID of the HWS to set to boost mode
        """
        self.logger.debug("emeraldhws: Sending control message: boost mode")
        self.sendControlMessage(id, {"mode": 0})

    def setQuietMode(self, id):
        """Sets the specified HWS to quiet (low power) mode
        :param id: The UUID of the HWS to set to quiet mode
        """
        self.logger.debug("emeraldhws: Sending control message: quiet mode")
        self.sendControlMessage(id, {"mode": 2})

    def isOn(self, id):
        """Returns true if the specified HWS is currently on
        :param id: The UUID of the HWS to query
        """
        full_status = self.getFullStatus(id)
        if full_status and full_status.get("last_state"):
            switch_status = full_status.get("last_state").get("switch")
            return switch_status == 1 or switch_status == "on"
        return False

    def isHeating(self, id):
        """Returns true if the specified HWS is currently heating
        :param id: The UUID of the HWS to query
        """
        full_status = self.getFullStatus(id)
        if full_status:
            # Try to get work_state from last_state (updated via MQTT)
            if full_status.get("last_state") and "work_state" in full_status.get(
                "last_state"
            ):
                work_state = full_status.get("last_state").get("work_state")
                # work_state: 0=off/idle, 1=actively heating, 2=on but not heating
                return work_state == 1

            # Fallback to device_operation_status if work_state not available yet
            # (e.g., before first MQTT update after initialisation)
            heating_status = full_status.get("device_operation_status")
            return heating_status == 1

        return False

    def getHourlyEnergyUsage(self, id):
        """Returns energy usage as reported by heater for the previous hour in kWh
        :param id: The UUID of the HWS to query
        """
        full_status = self.getFullStatus(id)
        if not full_status:
            return None

        consumption = json.loads(full_status.get("consumption_data", "{}"))
        return consumption.get("current_hour")

    def getDailyEnergyUsage(self, id):
        """Returns today's cumulative energy usage in kWh if available, otherwise None
        :param id: The UUID of the HWS to query
        :returns: Today's energy usage or None if no data received for current day yet
        """
        full_status = self.getFullStatus(id)
        if not full_status:
            return None

        consumption = json.loads(full_status.get("consumption_data", "{}"))
        today = datetime.now().strftime("%Y-%m-%d")
        return consumption.get("past_seven_days", {}).get(today)

    def getWeeklyEnergyUsage(self, id):
        """Returns total cumulative energy usage for the past 7 days in kWh
        :param id: The UUID of the HWS to query
        """
        full_status = self.getFullStatus(id)
        if not full_status:
            return None

        consumption = json.loads(full_status.get("consumption_data", "{}"))
        return sum(consumption.get("past_seven_days", {}).values())

    def getMonthlyEnergyUsage(self, id):
        """Returns current month's cumulative energy usage in kWh if available, otherwise None
        :param id: The UUID of the HWS to query
        """
        full_status = self.getFullStatus(id)
        if not full_status:
            return None

        consumption = json.loads(full_status.get("consumption_data", "{}"))
        current_month = datetime.now().strftime("%Y-%m")
        return consumption.get("monthly_consumption", {}).get(current_month)

    def getHistoricalConsumption(self, id):
        """Returns the full consumption data structure or None if unavailable
        :param id: The UUID of the HWS to query
        """
        full_status = self.getFullStatus(id)
        if not full_status:
            return None

        return json.loads(full_status.get("consumption_data", "{}"))

    def currentMode(self, id):
        """Returns an integer specifying the current mode (0==boost, 1==normal, 2==quiet)
        :param id: The UUID of the HWS to query
        """
        full_status = self.getFullStatus(id)
        if full_status and full_status.get("last_state"):
            mode_status = full_status.get("last_state").get("mode")
            return mode_status
        return None

    def getInfo(self, id):
        """Returns identifying details for the specified HWS
        :param id: The UUID of the HWS to query
        """
        full_status = self.getFullStatus(id)
        if full_status:
            return {
                "id": id,
                "serial_number": full_status.get("serial_number"),
                "brand": full_status.get("brand"),
                "hw_version": full_status.get("hw_version"),
                "soft_version": full_status.get("soft_version"),
            }
        return None

    def listHWS(self):
        """Returns a list of UUIDs of all discovered HWS"""
        if not self._is_connected:
            self.connect()

        properties_list = self._wait_for_properties()
        hws = []

        for properties in properties_list:
            heat_pumps = properties.get("heat_pump", [])
            for heat_pump in heat_pumps:
                hws.append(heat_pump["id"])

        return hws

    def subscribeAllHWS(self):
        """Subscribes to updates from all detected HWS"""

        properties_list = self._wait_for_properties()
        for property in properties_list:
            for hws in property.get("heat_pump"):
                self.subscribeForUpdates(hws.get("id"))

    def connect(self):
        """Connect to the API with the supplied credentials, retrieve HWS details
        :returns: True if successful
        """
        # Use lock to ensure only one thread can connect at a time
        with self._connect_lock:
            # Double-check pattern: check again inside the lock
            if self._is_connected:
                self.logger.debug("emeraldhws: Already connected, skipping")
                return

            self.logger.debug("emeraldhws: Connecting...")
            self.getLoginToken()
            self.getAllHWS()
            self.connectMQTT()
            self.subscribeAllHWS()
            self._is_connected = True

            # Start timers ONCE on initial connection
            if self.connection_timeout > 0:
                self.reconnect_timer = threading.Timer(
                    self.connection_timeout, self.scheduled_reconnect
                )
                self.reconnect_timer.daemon = True
                self.reconnect_timer.start()

            if self.health_check_interval > 0:
                self.health_check_timer = threading.Timer(
                    self.health_check_interval, self.check_connection_health
                )
                self.health_check_timer.daemon = True
                self.health_check_timer.start()
