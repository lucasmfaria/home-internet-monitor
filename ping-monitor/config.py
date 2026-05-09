"""
Configuration loader for the Ping Monitor service.
All values are read from environment variables with sensible defaults.
"""

import os

# InfluxDB connection
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://influxdb:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "home-monitor")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "internet_monitor")

# Ping settings
PING_TARGETS = os.getenv("PING_TARGETS", "8.8.8.8,1.1.1.1,208.67.222.222").split(",")
PING_INTERVAL = int(os.getenv("PING_INTERVAL", "5"))
PING_TIMEOUT = int(os.getenv("PING_TIMEOUT", "2"))
CONSECUTIVE_FAILURES_THRESHOLD = int(os.getenv("CONSECUTIVE_FAILURES_THRESHOLD", "3"))

# Telegram alerting
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
