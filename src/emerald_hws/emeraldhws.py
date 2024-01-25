import json
import requests
# import logging
import boto3
import random
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient


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

    def __init__(self, email, password):
        """ Initialise the API client
        :param email: The email address for logging into the Emerald app
        :param password: The password for the supplied user account
        """

        self.email = email
        self.password = password
        self.token = ""
        self.properties = {}

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
            self.properties = post_response_json.get("info").get("property")
        else:
            raise Exception("Unable to fetch properties from Emerald API")

    def connectMQTT(self):
        """ Establishes a connection to Amazon IOT core's MQTT service
        """

        # Cognito auth
        identityPoolID = self.COGNITO_IDENTITY_POOL_ID
        region = self.MQTT_HOST.split('.')[2]
        cognitoIdentityClient = boto3.client('cognito-identity', region_name=region)

        temporaryIdentityId = cognitoIdentityClient.get_id(IdentityPoolId=identityPoolID)
        identityID = temporaryIdentityId["IdentityId"]

        temporaryCredentials = cognitoIdentityClient.get_credentials_for_identity(IdentityId=identityID)
        AccessKeyId = temporaryCredentials["Credentials"]["AccessKeyId"]
        SecretKey = temporaryCredentials["Credentials"]["SecretKey"]
        SessionToken = temporaryCredentials["Credentials"]["SessionToken"]

        # Init AWSIoTMQTTClient
        myAWSIoTMQTTClient = AWSIoTMQTTClient(identityID, useWebsocket=True)

        # AWSIoTMQTTClient configuration
        myAWSIoTMQTTClient.configureEndpoint(self.MQTT_HOST, 443)
        myAWSIoTMQTTClient.configureCredentials("./SFSRootCAG2.pem")
        myAWSIoTMQTTClient.configureIAMCredentials(AccessKeyId, SecretKey, SessionToken)
        myAWSIoTMQTTClient.configureAutoReconnectBackoffTime(1, 32, 20)
        myAWSIoTMQTTClient.configureOfflinePublishQueueing(-1)  # Infinite offline Publish queueing
        myAWSIoTMQTTClient.configureDrainingFrequency(2)  # Draining: 2 Hz
        myAWSIoTMQTTClient.configureConnectDisconnectTimeout(10)  # 10 sec
        myAWSIoTMQTTClient.configureMQTTOperationTimeout(10)  # 10 sec

        # Connect and subscribe to AWS IoT
        myAWSIoTMQTTClient.connect()

        self.myAWSIoTMQTTClient = myAWSIoTMQTTClient

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

    def mqttCallback(self, client, userdata, message):
        # print("Received a new message: ")
        # print(message.payload.decode("utf-8"))
        # print("from topic: ")
        # print(message.topic)
        # print("--------------\n\n")

        self.mqttDecodeUpdate(message.topic, message.payload)

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

    def subscribeForUpdates(self, id):
        """ Subscribes to the MQTT topics for the supplied HWS
        :param id: The UUID of the requested HWS
        """
        if not self.myAWSIoTMQTTClient:
            self.connectMQTT()

        # self.myAWSIoTMQTTClient.subscribe("ep/heat_pump/to_gw/{}".format(id), 1, self.mqttCallback)
        self.myAWSIoTMQTTClient.subscribe("ep/heat_pump/from_gw/{}".format(id), 1, self.mqttCallback)
        # self.myAWSIoTMQTTClient.subscribe("ep/heat_pump/custom/topic/{}".format(id), 1, self.mqttCallback)

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

        self.myAWSIoTMQTTClient.publish("ep/heat_pump/to_gw/{}".format(id), json.dumps(msg), 1)

    def turnOn(self, id):
        """ Turns the specified HWS on
        :param id: The UUID of the HWS to turn on
        """
        self.sendControlMessage(id, {"switch":1})

    def turnOff(self, id):
        """ Turns the specified HWS off
        :param id: The UUID of the HWS to turn off
        """
        self.sendControlMessage(id, {"switch":0})

    def setNormalMode(self, id):
        """ Sets the specified HWS to normal (not Boost or Quiet) mode
        :param id: The UUID of the HWS to set to normal mode
        """
        self.sendControlMessage(id, {"mode":1})

    def setBoostMode(self, id):
        """ Sets the specified HWS to boost (high power) mode
        :param id: The UUID of the HWS to set to boost mode
        """
        self.sendControlMessage(id, {"mode":0})

    def setQuietMode(self, id):
        """ Sets the specified HWS to quiet (low power) mode
        :param id: The UUID of the HWS to set to quiet mode
        """
        self.sendControlMessage(id, {"mode":2})

    def isOn(self, id):
        """ Returns true if the specified HWS is currently on
        :param id: The UUID of the HWS to query
        """
        switch_status = self.getFullStatus(id).get("last_state").get("switch")
        return (switch_status == 1 or switch_status == "on")

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
