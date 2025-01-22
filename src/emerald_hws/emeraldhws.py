import json
import requests
import os
import logging
import boto3
import random
import threading
from awsiot import mqtt5_client_builder, mqtt_connection_builder
from awscrt import mqtt5, http, auth, io


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

    def __init__(self, email, password, update_callback=None):
        """ Initialise the API client
        :param email: The email address for logging into the Emerald app
        :param password: The password for the supplied user account
        :param update_callback: Optional callback function to be called when an update is available
        """

        self.email = email
        self.password = password
        self.token = ""
        self.properties = {}
        self.logger = logging.getLogger()
        self.update_callback = update_callback

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

    def reconnectMQTT(self):
        """ Stops an existing MQTT connection and creates a new one
        """

        self.logger.debug("emeraldhws: awsiot: Tearing down and reconnecting to prevent stale connection")
        self.mqttClient.stop()
        self.connectMQTT()
        self.subscribeAllHWS()

    def connectMQTT(self):
        """ Establishes a connection to Amazon IOT core's MQTT service
        """

        cert_path = os.path.join(os.path.dirname(__file__), '__assets__', 'SFSRootCAG2.pem')
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
        threading.Timer(43200.0, self.reconnectMQTT).start() # 12 hours

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
        self.mqttDecodeUpdate(publish_packet.topic, publish_packet.payload)

    def on_connection_interrupted(self, connection, error, **kwargs):
        """ Log error when MQTT is interrupted
        """
        self.logger.debug("emeraldhws: awsiot: Connection interrupted. error: {}".format(error))

    def on_connection_resumed(self, connection, return_code, session_present, **kwargs):
        """ Log message when MQTT is resumed
        """
        self.logger.debug("emeraldhws: awsiot: Connection resumed. return_code: {} session_present: {}".format(return_code, session_present))

    def on_lifecycle_connection_success(self, lifecycle_connect_success_data: mqtt5.LifecycleConnectSuccessData):
        """ Log message when connection succeeded
        """
        self.logger.debug("emeraldhws: awsiot: connection succeeded")
        return

    def on_lifecycle_connection_failure(self, lifecycle_connection_failure: mqtt5.LifecycleConnectFailureData):
        """ Log message when connection failed
        """
        self.logger.debug("emeraldhws: awsiot: connection failed")
        return

    def on_lifecycle_stopped(self, lifecycle_stopped_data: mqtt5.LifecycleStoppedData):
        """ Log message when stopped
        """
        self.logger.debug("emeraldhws: awsiot: stopped")
        return

    def on_lifecycle_disconnection(self, lifecycle_disconnect_data: mqtt5.LifecycleDisconnectData):
        """ Log message when disconnected
        """
        self.logger.debug("emeraldhws: awsiot: disconnected")
        return

    def on_lifecycle_attempting_connect(self, lifecycle_attempting_connect_data: mqtt5.LifecycleAttemptingConnectData):
        """ Log message when attempting connect
        """
        self.logger.debug("emeraldhws: awsiot: attempting to connect")
        return

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
        if self.update_callback != None:
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

        suback = subscribe_future.result(20)

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
