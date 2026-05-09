"""
Ping Monitor — Continuous connectivity checker with InfluxDB logging and
Telegram alerts.

Pings multiple targets concurrently every N seconds. Detects outage windows by
tracking consecutive failures across all targets. Fires Telegram alerts on
connection drop and recovery, including exact downtime duration.
"""

import asyncio
import logging
import re
import sys
import time
from datetime import datetime, timezone

import aiohttp
import config
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# ─── Logging ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("ping-monitor")


# ─── State Machine ─────────────────────────────────────────
class ConnectionState:
    """Tracks the overall internet connection state."""

    def __init__(self, threshold: int):
        self.threshold = threshold
        self.consecutive_all_fail = 0
        self.is_down = False
        self.down_since: float | None = None

    def update(self, all_targets_failed: bool) -> str | None:
        """
        Update state with the latest ping cycle result.

        Returns:
            "drop"     — if we just transitioned to DOWN
            "recovery" — if we just transitioned to UP
            None       — no state change
        """
        if all_targets_failed:
            self.consecutive_all_fail += 1
            if not self.is_down and self.consecutive_all_fail >= self.threshold:
                self.is_down = True
                self.down_since = time.time()
                return "drop"
        else:
            self.consecutive_all_fail = 0
            if self.is_down:
                self.is_down = False
                self.down_since = None
                return "recovery"
        return None


# ─── Ping Executor ─────────────────────────────────────────
RTT_PATTERN = re.compile(r"time[=<](\d+\.?\d*)\s*ms")


async def ping_target(target: str, timeout: int) -> dict:
    """
    Ping a single target using the system `ping` command.

    Returns a dict with keys: target, success, rtt_ms
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping",
            "-c",
            "1",
            "-W",
            str(timeout),
            target,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout + 2)
        output = stdout.decode("utf-8", errors="replace")

        if proc.returncode == 0:
            match = RTT_PATTERN.search(output)
            rtt = float(match.group(1)) if match else 0.0
            return {"target": target, "success": True, "rtt_ms": rtt}
        else:
            return {"target": target, "success": False, "rtt_ms": 0.0}
    except (asyncio.TimeoutError, OSError) as e:
        logger.warning(f"Ping to {target} failed: {e}")
        return {"target": target, "success": False, "rtt_ms": 0.0}


async def ping_all_targets(targets: list[str], timeout: int) -> list[dict]:
    """Ping all targets concurrently."""
    tasks = [ping_target(t.strip(), timeout) for t in targets]
    return await asyncio.gather(*tasks)


# ─── InfluxDB Writer ──────────────────────────────────────
def create_influx_client() -> tuple[InfluxDBClient, any]:
    """Create InfluxDB client and write API."""
    client = InfluxDBClient(
        url=config.INFLUXDB_URL,
        token=config.INFLUXDB_TOKEN,
        org=config.INFLUXDB_ORG,
    )
    write_api = client.write_api(write_options=SYNCHRONOUS)
    return client, write_api


def write_ping_results(write_api, results: list[dict]):
    """Write individual ping results to InfluxDB."""
    points = []
    for r in results:
        p = (
            Point("ping_result")
            .tag("device", config.DEVICE_NAME)
            .tag("target", r["target"])
            .field("success", r["success"])
            .field("rtt_ms", r["rtt_ms"])
            .time(datetime.now(timezone.utc), WritePrecision.NS)
        )
        points.append(p)

    try:
        write_api.write(bucket=config.INFLUXDB_BUCKET, record=points)
    except Exception as e:
        logger.error(f"Failed to write ping results to InfluxDB: {e}")


def write_outage_event(write_api, event_type: str, duration_seconds: float = 0.0):
    """Write an outage event (drop or recovery) to InfluxDB."""
    p = (
        Point("outage_event")
        .tag("device", config.DEVICE_NAME)
        .tag("type", event_type)
        .field("duration_seconds", duration_seconds)
        .time(datetime.now(timezone.utc), WritePrecision.NS)
    )
    try:
        write_api.write(bucket=config.INFLUXDB_BUCKET, record=p)
        logger.info(
            f"Outage event written: type={event_type}, duration={duration_seconds:.1f}s"
        )
    except Exception as e:
        logger.error(f"Failed to write outage event to InfluxDB: {e}")


# ─── Telegram Alerter ─────────────────────────────────────
async def send_telegram_alert(message: str):
    """Send an alert message via the Telegram Bot API."""
    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID

    if not token or not chat_id:
        logger.warning("Telegram not configured — skipping alert.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    logger.info("Telegram alert sent successfully.")
                else:
                    body = await resp.text()
                    logger.error(f"Telegram alert failed ({resp.status}): {body}")
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")


def format_duration(seconds: float) -> str:
    """Format a duration in seconds to a human-readable string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


# ─── Main Loop ─────────────────────────────────────────────
async def wait_for_influxdb():
    """Wait until InfluxDB is reachable."""
    logger.info(f"Waiting for InfluxDB at {config.INFLUXDB_URL}...")
    while True:
        try:
            client = InfluxDBClient(
                url=config.INFLUXDB_URL,
                token=config.INFLUXDB_TOKEN,
                org=config.INFLUXDB_ORG,
            )
            health = client.health()
            if health.status == "pass":
                logger.info("InfluxDB is ready.")
                client.close()
                return
            client.close()
        except Exception:
            pass
        await asyncio.sleep(2)


async def main():
    logger.info("=" * 60)
    logger.info("  Ping Monitor starting")
    logger.info(f"  Device  : {config.DEVICE_NAME}")
    logger.info(f"  Targets : {config.PING_TARGETS}")
    logger.info(f"  Interval: {config.PING_INTERVAL}s")
    logger.info(f"  Timeout : {config.PING_TIMEOUT}s")
    logger.info(f"  Failure threshold: {config.CONSECUTIVE_FAILURES_THRESHOLD}")
    logger.info("=" * 60)

    await wait_for_influxdb()

    client, write_api = create_influx_client()
    state = ConnectionState(threshold=config.CONSECUTIVE_FAILURES_THRESHOLD)
    down_since_ts: datetime | None = None

    try:
        while True:
            cycle_start = time.monotonic()

            # Ping all targets
            results = await ping_all_targets(config.PING_TARGETS, config.PING_TIMEOUT)

            # Log results
            for r in results:
                status = "✓" if r["success"] else "✗"
                rtt = f"{r['rtt_ms']:.1f}ms" if r["success"] else "timeout"
                logger.debug(f"  {status} {r['target']}: {rtt}")

            # Write to InfluxDB
            write_ping_results(write_api, results)

            # Check connection state
            all_failed = all(not r["success"] for r in results)
            any_ok = any(r["success"] for r in results)

            if any_ok and not all_failed:
                avg_rtt = sum(r["rtt_ms"] for r in results if r["success"]) / max(
                    sum(1 for r in results if r["success"]), 1
                )
                logger.debug(f"  Connection OK — avg RTT: {avg_rtt:.1f}ms")

            transition = state.update(all_failed)

            if transition == "drop":
                down_since_ts = datetime.now(timezone.utc)
                ts_str = down_since_ts.strftime("%Y-%m-%d %H:%M:%S UTC")
                logger.warning(f"🔴 INTERNET DOWN detected at {ts_str}")

                write_outage_event(write_api, "drop")

                msg = (
                    "🔴 <b>Internet Connection DOWN</b>\n\n"
                    f"🖥️ <b>Device:</b> {config.DEVICE_NAME}\n"
                    f"⏰ <b>Time:</b> {ts_str}\n"
                    f"🎯 <b>All targets unreachable:</b>\n"
                    + "\n".join(f"  • {t}" for t in config.PING_TARGETS)
                )
                await send_telegram_alert(msg)

            elif transition == "recovery":
                now = datetime.now(timezone.utc)
                duration = (now - down_since_ts).total_seconds() if down_since_ts else 0
                ts_str = now.strftime("%Y-%m-%d %H:%M:%S UTC")
                dur_str = format_duration(duration)
                logger.info(f"🟢 INTERNET RESTORED at {ts_str} (down for {dur_str})")

                write_outage_event(write_api, "recovery", duration)

                msg = (
                    "🟢 <b>Internet Connection RESTORED</b>\n\n"
                    f"🖥️ <b>Device:</b> {config.DEVICE_NAME}\n"
                    f"⏰ <b>Time:</b> {ts_str}\n"
                    f"⏱️ <b>Total downtime:</b> {dur_str}\n"
                )
                await send_telegram_alert(msg)

                down_since_ts = None

            # Sleep for the remaining interval
            elapsed = time.monotonic() - cycle_start
            sleep_time = max(0, config.PING_INTERVAL - elapsed)
            await asyncio.sleep(sleep_time)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
