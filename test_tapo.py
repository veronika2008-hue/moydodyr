"""
Quick check: reads current power from ONE Tapo plug and prints it to the console.
Run this after filling in TAPO_EMAIL, TAPO_PASSWORD and the plug's IP in config.py.

Usage:
    python test_tapo.py
"""

import asyncio
from tapo import ApiClient
from config import TAPO_EMAIL, TAPO_PASSWORD, TAPO_DEVICES
from find_tapo_ip import resolve_ip


async def main():
    client = ApiClient(TAPO_EMAIL, TAPO_PASSWORD)

    for machine_id in TAPO_DEVICES:
        ip = await asyncio.to_thread(resolve_ip, machine_id)
        print(f"\nConnecting to {machine_id} ({ip})...")
        try:
            device = await client.p110(ip)
            info = await device.get_current_power()
            watts = info.current_power
            print(f"  ✅ Success! Current power: {watts:.2f} W")
        except Exception as e:
            print(f"  ❌ Could not connect: {e}")


if __name__ == "__main__":
    asyncio.run(main())
