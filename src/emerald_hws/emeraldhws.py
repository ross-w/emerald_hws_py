import json
import logging
import os
import random
import threading
import time

import boto3
import requests
from awscrt import mqtt5, auth, io
from awsiot import mqtt5_client_builder


class EmeraldHWS():
    """ Implementation of the web API for Emerald Heat Pump Hot Water Systems
    """
    COMMON_HEADERS = {
        "accept":           "*/*",
        "content-type":     "application/json",
        "user-agent":       "EmeraldPlanet/2.5.3 (com.emerald-ems.customer; build:5; iOS 17.2.1) Alamofire/5.4.1",
        "accept-language":  "en-GB;q=1.0, en-AU;q=0.9",
    }

    MQTT_HOST = "a13v32g67itvz9-ats.iot.ap-southeast-2.amazonaws.com"
    COGNITO_IDENTITY_POOL_ID = "ap-southeast-2:f5bbb02c-c00e-4f10-acb3-e7d1b05268e8"

    def __init__(self, email, password, update_callback=None, connection_timeout_minutes=720, health_check_minutes=60):
        """ Initialise the API client
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
        self.logger = logging.getLogger("emerald_hws")
        self.update_callback = update_callback
        
        # Convert minutes to seconds for internal use
        self.connection_timeout = connection_timeout_minutes * 60.0
        self.health_check_interval = health_check_minutes * 60.0 if health_check_minutes > 0 else 0
        self.last_message_time = None
        self.health_check_timer = None
        
        # Connection state tracking
        self.connection_state = "initial"  # possible states: initial, connected, failed
        self.consecutive_failures = 0
        self.max_backoff_seconds = 60  # Maximum backoff of 1 minute
        
        # Ensure reasonable minimum values (e.g., at least 5 minutes for connection timeout)
        if connection_timeout_minutes < 5 and connection_timeout_minutes != 0:
            self.logger.warning("emeraldhws: Connection timeout too short, setting to minimum of 5 minutes")
            self.connection_timeout = 5 * 60.0
        
        # Ensure reasonable minimum values for health check (e.g., at least 5 minutes)
        if 0 < health_check_minutes < 5:
            self.logger.warning("emeraldhws: Health check interval too short, setting to minimum of 5 minutes")
            self.health_check_interval = 5 * 60.0

    def getLoginToken(self):
        """ Performs an API request to get a token from the API
        """
        url = "https://api.emerald-ems.com.au/api/v1/customer/sign-in"

        payload = {
            "app_version": "2.5.3",
            "device_name": "iPhone15,2",
            "device_os_version": "17.2.1",
            "device_type": "iOS",
            "email": self.email,
            "password": self.password
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
        """ Interrogates the API to list out all hot water systems on the account
        """

        if not self.token:
            self.getLoginToken()

        url = "https://api.emerald-ems.com.au/api/v1/customer/property/list"
        headers = self.COMMON_HEADERS
        headers["authorization"] = "Bearer {}".format(self.token)

        post_response = requests.get(url, headers=headers)
        post_response_json = post_response.json()

        if post_response_json.get("code") == 200:
            self.logger.debug("emeraldhws: Successfully logged into Emerald API")
            self.properties = post_response_json.get("info").get("property")
        else:
            raise Exception("Unable to fetch properties from Emerald API")

    def replaceCallback(self, update_callback):
        """ Replaces the current registered update callback (if any) with the supplied
        """

        self.update_callback = update_callback

    def reconnectMQTT(self, reason="scheduled"):
        """ Stops an existing MQTT connection and creates a new one
        :param reason: Reason for reconnection (scheduled, health_check, etc.)
        """
        self.logger.info(f"emeraldhws: awsiot: Reconnecting MQTT connection (reason: {reason})")
        
        # Store current temperature values for comparison after reconnect
        temp_values = {}
        for properties in self.properties:
            heat_pumps = properties.get('heat_pump', [])
            for heat_pump in heat_pumps:
                hws_id = heat_pump['id']
                if 'last_state' in heat_pump and 'temp_current' in heat_pump['last_state']:
                    temp_values[hws_id] = heat_pump['last_state']['temp_current']
        
        self.mqttClient.stop()
        self.connectMQTT()
        self.subscribeAllHWS()
        
        # After reconnection, check if temperatures have changed
        def check_temp_changes():
            for properties in self.properties:
                heat_pumps = properties.get('heat_pump', [])
                for heat_pump in heat_pumps:
                    hws_id = heat_pump['id']
                    if (hws_id in temp_values and 
                        'last_state' in heat_pump and 
                        'temp_current' in heat_pump['last_state']):
                        old_temp = temp_values[hws_id]
                        new_temp = heat_pump['last_state']['temp_current']
                        if old_temp != new_temp:
                            self.logger.info(f"emeraldhws: Temperature changed after reconnect for {hws_id}: {old_temp} → {new_temp}")
        
        # Check for temperature changes after a short delay to allow for updates
        threading.Timer(10.0, check_temp_changes).start()

    def connectMQTT(self):
        """ Establishes a connection to Amazon IOT core's MQTT service
        """

        # Certificate path is available but not currently used in the connection
        # os.path.join(os.path.dirname(__file__), '__assets__', 'SFSRootCAG2.pem')
        identityPoolID = self.COGNITO_IDENTITY_POOL_ID
        region = self.MQTT_HOST.split('.')[2]
        cognito_endpoint = "cognito-identity." + region + ".amazonaws.com"
        cognitoIdentityClient = boto3.client('cognito-identity', region_name=region)

        temporaryIdentityId = cognitoIdentityClient.get_id(IdentityPoolId=identityPoolID)
        identityID = temporaryIdentityId["IdentityId"]
        self.logger.debug("emeraldhws: awsiot: AWS IoT IdentityID: {}".format(identityID))

        credentials_provider = auth.AwsCredentialsProvider.new_cognito(
                endpoint=cognito_endpoint,
                identity=identityID,
                tls_ctx=io.ClientTlsContext(io.TlsContextOptions()))

        client = mqtt5_client_builder.websockets_with_default_aws_signing(
            endpoint = self.MQTT_HOST,
            region = region,
            credentials_provider = credentials_provider,
            on_connection_interrupted = self.on_connection_interrupted,
            on_connection_resumed = self.on_connection_resumed,
            on_lifecycle_connection_success = self.on_lifecycle_connection_success,
            on_lifecycle_stopped = self.on_lifecycle_stopped,
            on_lifecycle_attempting_connect = self.on_lifecycle_attempting_connect,
            on_lifecycle_disconnection = self.on_lifecycle_disconnection,
            on_lifecycle_connection_failure = self.on_lifecycle_connection_failure,
            on_publish_received = self.mqttCallback
        )

        client.start()
        self.mqttClient = client
        
        # Schedule periodic reconnection using configurable timeout
        if self.connection_timeout > 0:
            threading.Timer(self.connection_timeout, self.reconnectMQTT).start()
        
        # Start health check timer if enabled
        if self.health_check_interval > 0:
            self.health_check_timer = threading.Timer(self.health_check_interval, self.check_connection_health)
            self.health_check_timer.daemon = True
            self.health_check_timer.start()

    def mqttDecodeUpdate(self, topic, payload):
        """ Attempt to decode a received MQTT message and direct appropriately
        :param topic: MQTT topic
        :param payload: MQTT payload
        """
        json_payload = json.loads(payload.decode("utf-8"))
        hws_id = topic.split('/')[-1]

        command = json_payload[0].get("command")
        if command is not None:
            if command == "upload_status":
                for key in json_payload[1]:
                    self.updateHWSState(hws_id, key, json_payload[1][key])

    def mqttCallback(self, publish_packet_data):
        """ Calls decode update for received message
        """
        publish_packet = publish_packet_data.publish_packet
        assert isinstance(publish_packet, mqtt5.PublishPacket)
        self.logger.debug("emeraldhws: awsiot: Received message from MQTT topic {}: {}".format(publish_packet.topic, publish_packet.payload))
        self.last_message_time = time.time()  # Update the last message time
        self.mqttDecodeUpdate(publish_packet.topic, publish_packet.payload)

    def on_connection_interrupted(self, connection, error, **kwargs):
        """ Log error when MQTT is interrupted
        """
        error_code = getattr(error, 'code', 'unknown')
        error_name = getattr(error, 'name', 'unknown')
        self.logger.info(f"emeraldhws: awsiot: Connection interrupted. Error: {error_name} (code: {error_code}), Message: {error}")

    def on_connection_resumed(self, connection, return_code, session_present, **kwargs):
        """ Log message when MQTT is resumed
        """
        self.logger.debug("emeraldhws: awsiot: Connection resumed. return_code: {} session_present: {}".format(return_code, session_present))

    def on_lifecycle_connection_success(self, lifecycle_connect_success_data: mqtt5.LifecycleConnectSuccessData):
        """ Log message when connection succeeded
        """
        self.logger.debug("emeraldhws: awsiot: connection succeeded")
        # Reset failure counter and update connection state
        self.consecutive_failures = 0
        self.connection_state = "connected"
        return

    def on_lifecycle_connection_failure(self, lifecycle_connection_failure: mqtt5.LifecycleConnectFailureData):
        """ Log message when connection failed
        """
        error = lifecycle_connection_failure.error
        error_code = getattr(error, 'code', 'unknown')
        error_name = getattr(error, 'name', 'unknown')
        error_message = str(error)
        
        # Update connection state and increment failure counter
        self.connection_state = "failed"
        self.consecutive_failures += 1
        
        # Log at INFO level since this is important for troubleshooting
        self.logger.info(f"emeraldhws: awsiot: connection failed - Error: {error_name} (code: {error_code}), Message: {error_message}")
        
        # If there's a CONNACK packet available, log its details too
        if hasattr(lifecycle_connection_failure, 'connack_packet') and lifecycle_connection_failure.connack_packet:
            connack = lifecycle_connection_failure.connack_packet
            reason_code = getattr(connack, 'reason_code', 'unknown')
            reason_string = getattr(connack, 'reason_string', '')
            if reason_string:
                self.logger.info(f"emeraldhws: awsiot: MQTT CONNACK reason: {reason_code} - {reason_string}")
            else:
                self.logger.info(f"emeraldhws: awsiot: MQTT CONNACK reason code: {reason_code}")
        return

    def on_lifecycle_stopped(self, lifecycle_stopped_data: mqtt5.LifecycleStoppedData):
        """ Log message when stopped
        """
        self.logger.debug("emeraldhws: awsiot: stopped")
        return

    def on_lifecycle_disconnection(self, lifecycle_disconnect_data: mqtt5.LifecycleDisconnectData):
        """ Log message when disconnected
        """
        # Extract disconnect reason if available
        reason = "unknown reason"
        if hasattr(lifecycle_disconnect_data, 'disconnect_packet') and lifecycle_disconnect_data.disconnect_packet:
            reason_code = getattr(lifecycle_disconnect_data.disconnect_packet, 'reason_code', 'unknown')
            reason_string = getattr(lifecycle_disconnect_data.disconnect_packet, 'reason_string', '')
            reason = f"reason code: {reason_code}" + (f" - {reason_string}" if reason_string else "")
        
        self.logger.info(f"emeraldhws: awsiot: disconnected - {reason}")
        return

    def on_lifecycle_attempting_connect(self, lifecycle_attempting_connect_data: mqtt5.LifecycleAttemptingConnectData):
        """ Log message when attempting connect
        """
        # Include endpoint information if available
        endpoint = getattr(lifecycle_attempting_connect_data, 'endpoint', 'unknown')
        self.logger.debug(f"emeraldhws: awsiot: attempting to connect to {endpoint}")
        return
        
    def check_connection_health(self):
        """ Check if we've received any messages recently, reconnect if not
        """
        if self.last_message_time is None:
            # No messages received yet, don't reconnect
            self.logger.debug("emeraldhws: awsiot: Health check - No messages received yet")
        else:
            current_time = time.time()
            time_since_last_message = current_time - self.last_message_time
            minutes_since_last = time_since_last_message / 60.0
            
            if time_since_last_message > self.health_check_interval:
                # This is an INFO level log because it's an important event
                self.logger.info(f"emeraldhws: awsiot: No messages received for {minutes_since_last:.1f} minutes, reconnecting")
                
                # If we're in a failed state, apply exponential backoff
                if self.connection_state == "failed" and self.consecutive_failures > 0:
                    # Calculate backoff time with exponential increase, capped at max_backoff_seconds
                    backoff_seconds = min(2 ** (self.consecutive_failures - 1), self.max_backoff_seconds)
                    self.logger.info(f"emeraldhws: awsiot: Connection in failed state, applying backoff of {backoff_seconds} seconds before retry (attempt {self.consecutive_failures})")
                    time.sleep(backoff_seconds)
                
                self.reconnectMQTT(reason="health_check")
            else:
                # This is a DEBUG level log to avoid cluttering logs
                self.logger.debug(f"emeraldhws: awsiot: Health check - Last message received {minutes_since_last:.1f} minutes ago")
        
        # Schedule next health check
        if self.health_check_interval > 0:
            self.health_check_timer = threading.Timer(self.health_check_interval, self.check_connection_health)
            self.health_check_timer.daemon = True
            self.health_check_timer.start()

    def updateHWSState(self, id, key, value):
        """ Updates the specified value for the supplied key in the HWS id specified
        :param id: ID of the HWS
        :param key: key to update (eg temp_current)
        :param value: value to set
        """

        for properties in self.properties:
            heat_pumps = properties.get('heat_pump', [])
            for heat_pump in heat_pumps:
                if heat_pump['id'] == id:
                    heat_pump['last_state'][key] = value
        if self.update_callback is not None:
            self.update_callback()

    def subscribeForUpdates(self, id):
        """ Subscribes to the MQTT topics for the supplied HWS
        :param id: The UUID of the requested HWS
        """
        if not self.mqttClient:
            self.connectMQTT()

        mqtt_topic = "ep/heat_pump/from_gw/{}".format(id)
        subscribe_future = self.mqttClient.subscribe(
                subscribe_packet=mqtt5.SubscribePacket(
                        subscriptions=[mqtt5.Subscription(
                        topic_filter=mqtt_topic,
                        qos=mqtt5.QoS.AT_LEAST_ONCE)]))

        # Wait for subscription to complete
        subscribe_future.result(20)

    def getFullStatus(self, id):
        """ Returns a dict with the full status of the specified HWS
        :param id: UUID of the HWS to get the status for
        """

        if not self.properties:
            self.connect()

        for properties in self.properties:
            heat_pumps = properties.get('heat_pump', [])
            for heat_pump in heat_pumps:
                if heat_pump['id'] == id:
                    return heat_pump

    def sendControlMessage(self, id, payload):
        """ Sends a message via MQTT to the HWS
        :param id: The UUID of the requested HWS
        :param payload: JSON payload to send eg {"switch":1}
        """

        if not self.properties:
            self.connect()

        hwsdetail = self.getFullStatus(id)

        msg = [{"device_id":id,
                "namespace":"business",
                "direction":"app2gw",
                "property_id":hwsdetail.get("property_id"),
                "command":"control",
                "hw_id":hwsdetail.get("mac_address"),
                "msg_id":"{}".format(random.randint(100, 9999))
               },
               payload
              ]
        mqtt_topic = "ep/heat_pump/to_gw/{}".format(id)
        publish_future = self.mqttClient.publish(
                mqtt5.PublishPacket(
                        topic=mqtt_topic,
                        payload=json.dumps(msg),
                        qos=mqtt5.QoS.AT_LEAST_ONCE))
        publish_future.result(20) # 20 seconds

    def turnOn(self, id):
        """ Turns the specified HWS on
        :param id: The UUID of the HWS to turn on
        """
        self.logger.debug("emeraldhws: Sending control message: turn on")
        self.sendControlMessage(id, {"switch":1})

    def turnOff(self, id):
        """ Turns the specified HWS off
        :param id: The UUID of the HWS to turn off
        """
        self.logger.debug("emeraldhws: Sending control message: turn off")
        self.sendControlMessage(id, {"switch":0})

    def setNormalMode(self, id):
        """ Sets the specified HWS to normal (not Boost or Quiet) mode
        :param id: The UUID of the HWS to set to normal mode
        """
        self.logger.debug("emeraldhws: Sending control message: normal mode")
        self.sendControlMessage(id, {"mode":1})

    def setBoostMode(self, id):
        """ Sets the specified HWS to boost (high power) mode
        :param id: The UUID of the HWS to set to boost mode
        """
        self.logger.debug("emeraldhws: Sending control message: boost mode")
        self.sendControlMessage(id, {"mode":0})

    def setQuietMode(self, id):
        """ Sets the specified HWS to quiet (low power) mode
        :param id: The UUID of the HWS to set to quiet mode
        """
        self.logger.debug("emeraldhws: Sending control message: quiet mode")
        self.sendControlMessage(id, {"mode":2})

    def isOn(self, id):
        """ Returns true if the specified HWS is currently on
        :param id: The UUID of the HWS to query
        """
        switch_status = self.getFullStatus(id).get("last_state").get("switch")
        return (switch_status == 1 or switch_status == "on")

    def isHeating(self, id):
        """ Returns true if the specified HWS is currently heating
        :param id: The UUID of the HWS to query
        """
        heating_status = self.getFullStatus(id).get("device_operation_status")
        return (heating_status == 1)

    def currentMode(self, id):
        """ Returns an integer specifying the current mode (0==boost, 1==normal, 2==quiet)
        :param id: The UUID of the HWS to query
        """
        mode_status = self.getFullStatus(id).get("last_state").get("mode")
        return mode_status

    def getInfo(self, id):
        """ Returns identifying details for the specified HWS
        :param id: The UUID of the HWS to query
        """
        full_status = self.getFullStatus(id)

        return {'id': id,
                'serial_number': full_status.get("serial_number"),
                'brand': full_status.get("brand"),
                'hw_version': full_status.get("hw_version"),
                'soft_version': full_status.get("soft_version")
                }

    def listHWS(self):
        """ Returns a list of UUIDs of all discovered HWS
        """
        if not self.properties:
            self.connect()

        hws = []

        for properties in self.properties:
            heat_pumps = properties.get('heat_pump', [])
            for heat_pump in heat_pumps:
                hws.append(heat_pump["id"])

        return hws

    def subscribeAllHWS(self):
        """ Subscribes to updates from all detected HWS
        """

        if not self.properties:
            self.getAllHWS()

        for property in self.properties:
            for hws in property.get("heat_pump"):
                self.subscribeForUpdates(hws.get("id"))

    def connect(self):
        """ Connect to the API with the supplied credentials, retrieve HWS details
        :returns: True if successful
        """
        self.getLoginToken()
        self.getAllHWS()
        self.connectMQTT()
        self.subscribeAllHWS()
