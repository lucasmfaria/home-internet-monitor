# 🌐 Home Internet Monitor

Automated home internet monitoring system that continuously tracks your ISP's performance — connectivity uptime, micro-drops, bandwidth speeds, and latency — with real-time Grafana dashboards and Telegram alerts.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Docker Compose Stack                  │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Ping Monitor │  │ Speed Tester │  │   Grafana    │  │
│  │  (Python)    │  │ (Python +    │  │  (Port 3000) │  │
│  │  every 5s    │  │  Ookla CLI)  │  │              │  │
│  │              │  │  every 30m   │  │  13 Panels   │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                 │                 │           │
│         └────────┬────────┘                 │           │
│                  ▼                          │           │
│         ┌──────────────┐                    │           │
│         │  InfluxDB    │◄───────────────────┘           │
│         │  (Port 8086) │                                │
│         │  180d retain │                                │
│         └──────────────┘                                │
└─────────────────────────────────────────────────────────┘
                  │
                  ▼
         🔔 Telegram Alerts
         (drop / recovery)
```

## Tech Stack

| Component | Technology | Purpose |
|---|---|---|
| Database | InfluxDB 2.7 | Time-series storage optimized for high-write throughput |
| Dashboards | Grafana 11 OSS | Real-time visualization with pre-built panels |
| Ping Monitor | Python 3.12 (asyncio) | 5-second interval connectivity checks to multiple DNS servers |
| Speed Tester | Ookla Speedtest CLI | Accurate bandwidth measurement every 30 minutes |
| Alerting | Telegram Bot API | Instant notifications on connection drop and recovery |
| Orchestration | Docker Compose | Single-command deployment with health checks |

## Quick Start

### 1. Clone and configure

```bash
cd home-internet-monitor
cp .env.example .env
```

Edit `.env` with your values:
- Set strong passwords for `INFLUXDB_ADMIN_PASSWORD` and `INFLUXDB_ADMIN_TOKEN`
- Set `GRAFANA_ADMIN_PASSWORD`
- Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` for alerts

### 2. Start the stack

```bash
docker compose up -d
```

This will:
- Pull/build all 4 containers
- Initialize InfluxDB with the `internet_monitor` bucket (180-day retention)
- Start pinging every 5 seconds immediately
- Run the first speed test within 1 minute
- Make Grafana available at `http://localhost:3000`

### 3. Access Grafana

Open `http://<server-ip>:3000` and log in with your configured credentials.
The **Internet Monitor** dashboard is auto-provisioned as the home dashboard.

### 4. (Optional) Set up downsampling tasks

For long-term aggregated data, run the setup script once:

```bash
source .env
INFLUXDB_ADMIN_TOKEN=$INFLUXDB_ADMIN_TOKEN \
  INFLUXDB_URL=http://localhost:8086 \
  bash influxdb/setup-tasks.sh
```

## Telegram Bot Setup

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy the **bot token** → set as `TELEGRAM_BOT_TOKEN` in `.env`
4. Message [@userinfobot](https://t.me/userinfobot) to get your **chat ID** → set as `TELEGRAM_CHAT_ID`
5. Send any message to your new bot first (to initialize the chat)

### Alert Examples

- **🔴 Internet Connection DOWN** — timestamp + list of unreachable targets
- **🟢 Internet Connection RESTORED** — timestamp + exact downtime duration

## Dashboard Panels

| Panel | Description |
|---|---|
| Connection Status | Live UP/DOWN indicator |
| Uptime Gauges | 24h / 7d / 30d uptime percentages |
| Last Download/Upload | Most recent speed test results |
| Ping Latency (RTT) | Time-series graph per target |
| Connection State Timeline | Visual UP/DOWN state per target |
| Outage Events Table | Log of all drop/recovery events with duration |
| Download Speed Over Time | Bandwidth trend graph |
| Upload Speed Over Time | Bandwidth trend graph |
| Speed Test Latency & Jitter | Network quality metrics |
| Daily Uptime Report | Per-day uptime % table (last 30 days) |

## Configuration Reference

All configuration is via environment variables in `.env`:

| Variable | Default | Description |
|---|---|---|
| `PING_TARGETS` | `8.8.8.8,1.1.1.1,208.67.222.222` | Comma-separated ping targets |
| `PING_INTERVAL` | `5` | Seconds between ping cycles |
| `PING_TIMEOUT` | `2` | Per-ping timeout in seconds |
| `CONSECUTIVE_FAILURES_THRESHOLD` | `3` | Failed cycles before declaring outage |
| `SPEED_TEST_INTERVAL` | `30` | Minutes between speed tests |
| `DATA_RETENTION_DAYS` | `180` | InfluxDB data retention period |

## Useful InfluxDB Queries (Flux)

### Daily uptime percentage (last 30 days)
```flux
from(bucket: "internet_monitor")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "ping_result" and r._field == "success")
  |> aggregateWindow(every: 1d, fn: mean, createEmpty: false)
  |> map(fn: (r) => ({ r with _value: r._value * 100.0 }))
```

### Average speed per day
```flux
from(bucket: "internet_monitor")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "speed_test")
  |> filter(fn: (r) => r._field == "download_mbps" or r._field == "upload_mbps")
  |> aggregateWindow(every: 1d, fn: mean, createEmpty: false)
```

### List all outage events
```flux
from(bucket: "internet_monitor")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "outage_event")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"], desc: true)
```

## Maintenance

```bash
# View logs
docker compose logs -f ping-monitor
docker compose logs -f speed-tester

# Restart a single service
docker compose restart ping-monitor

# Stop everything
docker compose down

# Stop and remove data volumes (DESTRUCTIVE)
docker compose down -v
```

## License

MIT
