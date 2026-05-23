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

# Fetch Organization ID dynamically using the organization name
echo "Fetching organization ID for '${INFLUX_ORG}'..."
ORG_RESPONSE=$(curl -s -X GET "${INFLUX_HOST}/api/v2/orgs?org=${INFLUX_ORG}" \
  -H "Authorization: Token ${INFLUX_TOKEN}")

ORG_ID=$(echo "$ORG_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['orgs'][0]['id'])" 2>/dev/null || true)

if [ -z "$ORG_ID" ]; then
  echo "ERROR: Failed to retrieve organization ID for organization '${INFLUX_ORG}'."
  echo "Response: $ORG_RESPONSE"
  exit 1
fi

echo "Creating InfluxDB downsampling tasks (Org ID: $ORG_ID)..."

# ─── Hourly Rollup Task ────────────────────────────────────
cat <<'TASK_EOF' | sed -e "s/ORG_ID_PLACEHOLDER/$ORG_ID/g" -e "s/ORG_NAME_PLACEHOLDER/$INFLUX_ORG/g" | curl -s -X POST "${INFLUX_HOST}/api/v2/tasks" \
  -H "Authorization: Token ${INFLUX_TOKEN}" \
  -H "Content-Type: application/json" \
  -d @-
{
  "orgID": "ORG_ID_PLACEHOLDER",
  "org": "ORG_NAME_PLACEHOLDER",
  "name": "Hourly Ping Rollup",
  "every": "1h",
  "flux": "option task = {name: \"Hourly Ping Rollup\", every: 1h}\n\nfrom(bucket: \"internet_monitor\")\n  |> range(start: -1h)\n  |> filter(fn: (r) => r._measurement == \"ping_result\" and r._field == \"success\")\n  |> toFloat()\n  |> group(columns: [\"target\"])\n  |> mean()\n  |> map(fn: (r) => ({ r with _measurement: \"ping_hourly\", _field: \"uptime_pct\", _value: r._value * 100.0 }))\n  |> to(bucket: \"internet_monitor\", org: \"ORG_NAME_PLACEHOLDER\")"
}
TASK_EOF

echo ""
echo "  ✓ Hourly Ping Rollup task created"

# ─── Daily Summary Task ────────────────────────────────────
cat <<'TASK_EOF' | sed -e "s/ORG_ID_PLACEHOLDER/$ORG_ID/g" -e "s/ORG_NAME_PLACEHOLDER/$INFLUX_ORG/g" | curl -s -X POST "${INFLUX_HOST}/api/v2/tasks" \
  -H "Authorization: Token ${INFLUX_TOKEN}" \
  -H "Content-Type: application/json" \
  -d @-
{
  "orgID": "ORG_ID_PLACEHOLDER",
  "org": "ORG_NAME_PLACEHOLDER",
  "name": "Daily Summary Rollup",
  "every": "1d",
  "flux": "option task = {name: \"Daily Summary Rollup\", every: 1d}\n\nping_uptime = from(bucket: \"internet_monitor\")\n  |> range(start: -1d)\n  |> filter(fn: (r) => r._measurement == \"ping_result\" and r._field == \"success\")\n  |> toFloat()\n  |> group()\n  |> mean()\n  |> map(fn: (r) => ({ r with _measurement: \"daily_summary\", _field: \"uptime_pct\", _value: r._value * 100.0 }))\n  |> to(bucket: \"internet_monitor\", org: \"ORG_NAME_PLACEHOLDER\")\n\noutage_count = from(bucket: \"internet_monitor\")\n  |> range(start: -1d)\n  |> filter(fn: (r) => r._measurement == \"outage_event\" and r.type == \"drop\")\n  |> group()\n  |> count()\n  |> map(fn: (r) => ({ r with _measurement: \"daily_summary\", _field: \"outage_count\" }))\n  |> to(bucket: \"internet_monitor\", org: \"ORG_NAME_PLACEHOLDER\")"
}
TASK_EOF

echo ""
echo "  ✓ Daily Summary Rollup task created"
echo ""
echo "Done! Tasks are now running in InfluxDB."
