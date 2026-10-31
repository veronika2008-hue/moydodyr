"""
Logs power readings from one Tapo plug to a CSV file, for calibrating
STAGE_THRESHOLDS in tapo_source.py.

Usage:
    Start this script right when you start the wash cycle, let it run
    untouched for the whole cycle, then stop it with Ctrl+C once the
    machine is done. No need to write anything down while it runs — just
    hand the resulting CSV over afterward and the power segments will be
    read off it directly to pick threshold values.

    python calibrate.py [machine_id]

    machine_id defaults to the first entry in config.TAPO_DEVICES.
"""

import asyncio
import csv
import sys
from datetime import datetime

from tapo import ApiClient
from config import TAPO_EMAIL, TAPO_PASSWORD, TAPO_DEVICES
from find_tapo_ip import resolve_ip

POLL_INTERVAL_SECONDS = 3


async def main():
    machine_id = sys.argv[1] if len(sys.argv) > 1 else next(iter(TAPO_DEVICES))
    ip = await asyncio.to_thread(resolve_ip, machine_id)

    client = ApiClient(TAPO_EMAIL, TAPO_PASSWORD)
    device = await client.p110(ip)

    log_name = f"calibration_{machine_id.replace('№', 'n')}_{datetime.now():%Y%m%d_%H%M%S}.csv"
    print(f"Logging power for {machine_id} ({ip}) to {log_name}")
    print("Start the wash cycle now. Press Ctrl+C to stop.\n")

    start = datetime.now()
    with open(log_name, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["elapsed_seconds", "timestamp", "watts"])

        try:
            while True:
                try:
                    info = await device.get_current_power()
                    watts = info.current_power
                except Exception as e:
                    print(f"  (reconnecting after error: {e})")
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    try:
                        ip = await asyncio.to_thread(resolve_ip, machine_id)
                        device = await client.p110(ip)
                    except Exception as e2:
                        print(f"  (reconnect failed, will retry: {e2})")
                    continue

                elapsed = int((datetime.now() - start).total_seconds())
                writer.writerow([elapsed, datetime.now().isoformat(timespec="seconds"), watts])
                f.flush()
                print(f"  {elapsed:>5}s  {watts:>7.1f} W")
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print(f"\nStopped. Log saved to {log_name}")


if __name__ == "__main__":
    asyncio.run(main())
