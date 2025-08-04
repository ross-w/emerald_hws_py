# emerald_hws_py
Python package for controlling Emerald Heat Pump Hot Water Systems

## Overview
This package provides an interface to control and monitor Emerald Heat Pump Hot Water Systems through their API and MQTT service.

## Installation
```bash
pip install emerald_hws
```

## Usage
```python
from emerald_hws.emeraldhws import EmeraldHWS

# Basic usage with default connection settings
client = EmeraldHWS("your_email@example.com", "your_password")
client.connect()

# List all hot water systems
hws_list = client.listHWS()
print(f"Found {len(hws_list)} hot water systems")

# Get status of first HWS
hws_id = hws_list[0]
status = client.getFullStatus(hws_id)
print(f"Current temperature: {status['last_state'].get('temp_current')}")

# Turn on the hot water system
client.turnOn(hws_id)
```

## Configuration Options

### Connection Timeout
The module will automatically reconnect to the MQTT service periodically to prevent stale connections. You can configure this timeout:

```python
# Set connection timeout to 6 hours (360 minutes)
client = EmeraldHWS("your_email@example.com", "your_password", connection_timeout_minutes=360)
```

### Health Check
The module can proactively check for message activity and reconnect if no messages have been received for a specified period:

```python
# Set health check to check every 30 minutes
client = EmeraldHWS("your_email@example.com", "your_password", health_check_minutes=30)

# Disable health check
client = EmeraldHWS("your_email@example.com", "your_password", health_check_minutes=0)
```

## Callback for Updates
You can register a callback function to be notified when the state of any hot water system changes:

```python
def my_callback():
    print("Hot water system state updated!")

client = EmeraldHWS("your_email@example.com", "your_password", update_callback=my_callback)
```
