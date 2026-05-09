"""
Speed Tester — Automated bandwidth measurement with InfluxDB logging.

Uses the official Ookla Speedtest CLI to measure download/upload speeds and latency,
then writes the results to InfluxDB at a configurable interval.
"""

import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone

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
logger = logging.getLogger("speed-tester")


# ─── Speed Test Runner ─────────────────────────────────────
def run_speedtest() -> dict | None:
    """
    Execute the official Ookla Speedtest CLI and return parsed results.

    Returns None if the test fails.
    """
    try:
        logger.info("Running speed test...")
        result = subprocess.run(
            ["speedtest", "--format=json", "--accept-license", "--accept-gdpr"],
            capture_output=True,
            text=True,
            timeout=120,  # 2-minute timeout for slow connections
        )

        if result.returncode != 0:
            logger.error(
                f"Speedtest CLI failed (exit {result.returncode}): {result.stderr}"
            )
            return None

        data = json.loads(result.stdout)
        return data

    except subprocess.TimeoutExpired:
        logger.error("Speed test timed out after 120 seconds.")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse speedtest JSON output: {e}")
        return None
    except FileNotFoundError:
        logger.error("Speedtest CLI not found. Make sure it's installed.")
        return None
    except Exception as e:
        logger.error(f"Unexpected error running speed test: {e}")
        return None


def parse_results(data: dict) -> dict:
    """
    Parse the Ookla Speedtest JSON output into a clean dict.

    Ookla reports bandwidth in bytes/sec; we convert to Mbps.
    """
    # bandwidth: bytes/s → Mbps (multiply by 8 for bits, divide by 1e6 for mega)
    download_mbps = (data.get("download", {}).get("bandwidth", 0) * 8) / 1_000_000
    upload_mbps = (data.get("upload", {}).get("bandwidth", 0) * 8) / 1_000_000

    # Latency
    ping_data = data.get("ping", {})
    latency_ms = ping_data.get("latency", 0.0)
    jitter_ms = ping_data.get("jitter", 0.0)

    # Download/Upload specific latency (if available)
    dl_latency = data.get("download", {}).get("latency", {})
    ul_latency = data.get("upload", {}).get("latency", {})

    # Server info
    server = data.get("server", {})
    server_name = server.get("name", "unknown")
    server_id = str(server.get("id", "0"))
    server_location = server.get("location", "unknown")

    # ISP
    isp = data.get("isp", "unknown")

    # Packet loss (may not always be available)
    packet_loss = data.get("packetLoss", -1.0)

    # Result URL
    result_url = data.get("result", {}).get("url", "")

    return {
        "download_mbps": round(download_mbps, 2),
        "upload_mbps": round(upload_mbps, 2),
        "latency_ms": round(latency_ms, 2),
        "jitter_ms": round(jitter_ms, 2),
        "download_latency_ms": round(dl_latency.get("iqm", 0.0), 2),
        "upload_latency_ms": round(ul_latency.get("iqm", 0.0), 2),
        "packet_loss": round(packet_loss, 2) if packet_loss >= 0 else -1.0,
        "server_name": server_name,
        "server_id": server_id,
        "server_location": server_location,
        "isp": isp,
        "result_url": result_url,
    }


# ─── InfluxDB Writer ──────────────────────────────────────
def create_influx_client():
    """Create InfluxDB client and write API."""
    client = InfluxDBClient(
        url=config.INFLUXDB_URL,
        token=config.INFLUXDB_TOKEN,
        org=config.INFLUXDB_ORG,
    )
    write_api = client.write_api(write_options=SYNCHRONOUS)
    return client, write_api


def write_speed_results(write_api, results: dict):
    """Write speed test results to InfluxDB."""
    p = (
        Point("speed_test")
        .tag("server_name", results["server_name"])
        .tag("server_id", results["server_id"])
        .tag("server_location", results["server_location"])
        .tag("isp", results["isp"])
        .field("download_mbps", results["download_mbps"])
        .field("upload_mbps", results["upload_mbps"])
        .field("latency_ms", results["latency_ms"])
        .field("jitter_ms", results["jitter_ms"])
        .field("download_latency_ms", results["download_latency_ms"])
        .field("upload_latency_ms", results["upload_latency_ms"])
        .field("packet_loss", results["packet_loss"])
        .field("result_url", results["result_url"])
        .time(datetime.now(timezone.utc), WritePrecision.NS)
    )

    try:
        write_api.write(bucket=config.INFLUXDB_BUCKET, record=p)
        logger.info("Speed test results written to InfluxDB.")
    except Exception as e:
        logger.error(f"Failed to write speed test results to InfluxDB: {e}")


# ─── Wait for InfluxDB ────────────────────────────────────
def wait_for_influxdb():
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
        time.sleep(2)


# ─── Main Loop ─────────────────────────────────────────────
def main():
    logger.info("=" * 60)
    logger.info("  Speed Tester starting")
    logger.info(f"  Interval: every {config.SPEED_TEST_INTERVAL} minutes")
    logger.info("=" * 60)

    wait_for_influxdb()

    client, write_api = create_influx_client()
    interval_seconds = config.SPEED_TEST_INTERVAL * 60

    try:
        while True:
            test_start = time.monotonic()

            raw = run_speedtest()
            if raw:
                results = parse_results(raw)
                logger.info(
                    f"📊 Download: {results['download_mbps']} Mbps | "
                    f"Upload: {results['upload_mbps']} Mbps | "
                    f"Latency: {results['latency_ms']} ms | "
                    f"Jitter: {results['jitter_ms']} ms"
                )
                write_speed_results(write_api, results)
            else:
                logger.warning("Speed test failed — will retry next cycle.")

            # Sleep for the remaining interval
            elapsed = time.monotonic() - test_start
            sleep_time = max(0, interval_seconds - elapsed)
            logger.info(f"Next speed test in {sleep_time / 60:.0f} minutes.")
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        client.close()


if __name__ == "__main__":
    main()
