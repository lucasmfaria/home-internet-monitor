"""
Configuration loader for the Speed Tester service.
All values are read from environment variables with sensible defaults.
"""

import os

# InfluxDB connection
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://influxdb:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "home-monitor")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "internet_monitor")

# Speed test settings (interval in minutes)
SPEED_TEST_INTERVAL = int(os.getenv("SPEED_TEST_INTERVAL", "30"))
