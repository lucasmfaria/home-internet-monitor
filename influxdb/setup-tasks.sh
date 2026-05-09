#!/bin/bash
# ──────────────────────────────────────────────────────────
# InfluxDB Post-Setup: Create downsampling tasks
#
# Run this ONCE after the stack is up and InfluxDB is initialized:
#   docker exec influxdb bash /scripts/setup-tasks.sh
#
# Or run from the host:
#   bash influxdb/setup-tasks.sh
# ──────────────────────────────────────────────────────────

set -euo pipefail

INFLUX_HOST="${INFLUXDB_URL:-http://localhost:8086}"
INFLUX_TOKEN="${INFLUXDB_ADMIN_TOKEN:-}"
INFLUX_ORG="${INFLUXDB_ORG:-home-monitor}"

if [ -z "$INFLUX_TOKEN" ]; then
  echo "ERROR: INFLUXDB_ADMIN_TOKEN is required."
  echo "Usage: INFLUXDB_ADMIN_TOKEN=<token> bash setup-tasks.sh"
  exit 1
fi

echo "Creating InfluxDB downsampling tasks..."

# ─── Hourly Rollup Task ────────────────────────────────────
curl -s -X POST "${INFLUX_HOST}/api/v2/tasks" \
  -H "Authorization: Token ${INFLUX_TOKEN}" \
  -H "Content-Type: application/json" \
  -d @- <<'TASK_EOF'
{
  "orgID": "",
  "org": "home-monitor",
  "name": "Hourly Ping Rollup",
  "every": "1h",
  "flux": "option task = {name: \"Hourly Ping Rollup\", every: 1h}\n\nfrom(bucket: \"internet_monitor\")\n  |> range(start: -1h)\n  |> filter(fn: (r) => r._measurement == \"ping_result\" and r._field == \"success\")\n  |> group(columns: [\"target\"])\n  |> mean()\n  |> map(fn: (r) => ({ r with _measurement: \"ping_hourly\", _field: \"uptime_pct\", _value: r._value * 100.0 }))\n  |> to(bucket: \"internet_monitor\", org: \"home-monitor\")"
}
TASK_EOF

echo "  ✓ Hourly Ping Rollup task created"

# ─── Daily Summary Task ────────────────────────────────────
curl -s -X POST "${INFLUX_HOST}/api/v2/tasks" \
  -H "Authorization: Token ${INFLUX_TOKEN}" \
  -H "Content-Type: application/json" \
  -d @- <<'TASK_EOF'
{
  "orgID": "",
  "org": "home-monitor",
  "name": "Daily Summary Rollup",
  "every": "1d",
  "flux": "option task = {name: \"Daily Summary Rollup\", every: 1d}\n\nping_uptime = from(bucket: \"internet_monitor\")\n  |> range(start: -1d)\n  |> filter(fn: (r) => r._measurement == \"ping_result\" and r._field == \"success\")\n  |> group()\n  |> mean()\n  |> map(fn: (r) => ({ r with _measurement: \"daily_summary\", _field: \"uptime_pct\", _value: r._value * 100.0 }))\n  |> to(bucket: \"internet_monitor\", org: \"home-monitor\")\n\noutage_count = from(bucket: \"internet_monitor\")\n  |> range(start: -1d)\n  |> filter(fn: (r) => r._measurement == \"outage_event\" and r.type == \"drop\")\n  |> group()\n  |> count()\n  |> map(fn: (r) => ({ r with _measurement: \"daily_summary\", _field: \"outage_count\" }))\n  |> to(bucket: \"internet_monitor\", org: \"home-monitor\")"
}
TASK_EOF

echo "  ✓ Daily Summary Rollup task created"
echo ""
echo "Done! Tasks are now running in InfluxDB."
