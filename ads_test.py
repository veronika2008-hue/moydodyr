"""
First check of the ADS1115 on the Pi:
  1. reads each input A0..A3 against ground,
  2. measures how many readings per second actually come through I2C,
  3. takes a short differential A0 - A3 burst at the gain the current sensor will use.

With nothing wired to the inputs, the numbers in (1) and (3) are just noise
from floating pins — the point is that the chip answers and data flows.

Usage (on the Pi):  ~/moydodyr/venv/bin/python ads_test.py
"""

import math
import time

from ads1115 import ADS1115

adc = ADS1115()

print("1) Single-ended inputs (+/-4.096 V range):")
for pin in ("A0", "A1", "A2", "A3"):
    print(f"   {pin}: {adc.read_voltage(pin, 'GND', 4.096):+.4f} V")

print("\n2) Raw I2C read speed (continuous mode, 860 SPS):")
adc._write_config("A0", "A3", 0.512, 860, single_shot=False)
n = 0
t0 = time.perf_counter()
while time.perf_counter() - t0 < 2.0:
    adc._read_raw()
    n += 1
print(f"   {n / 2.0:.0f} reads per second over I2C")

print("\n3) Differential A0 - A3 (+/-0.512 V range), 1 second at 860 SPS:")
values = adc.sample("A0", "A3", 0.512, seconds=1.0)
mean = sum(values) / len(values)
rms = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
print(f"   {len(values)} readings, mean {mean * 1000:+.2f} mV, RMS around mean {rms * 1000:.2f} mV")
