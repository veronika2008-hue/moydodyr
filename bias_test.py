"""
Checks the low-voltage side of the current-sensing circuit, with no mains
involved: clamps plugged into their sockets but not around any cable.

  1. Bias on A3 should be ~1.65 V (half of 3.3 V from the 10k/10k divider).
  2. For each clamp input (A0..A2): the input pin should sit at the bias
     voltage too (the clamp connects it to the bias), and the difference
     input - A3 should be ~0 with only a little noise.

Usage (on the Pi):  ~/moydodyr/venv/bin/python bias_test.py [A0 A1 A2]
With no arguments, checks A0 only.
"""

import sys

from ads1115 import ADS1115
from sct_source import BIAS_INPUT, FULL_SCALE_V, rms_amps

adc = ADS1115()
inputs = sys.argv[1:] or ["A0"]


def verdict(ok: bool) -> str:
    return "OK   " if ok else "CHECK"


bias = adc.read_voltage(BIAS_INPUT, "GND", 4.096)
bias_ok = 1.5 <= bias <= 1.8
print(f"{verdict(bias_ok)} bias on {BIAS_INPUT}: {bias:.3f} V (expected ~1.65 V)")
if not bias_ok:
    print("      -> divider not powered, not connected to A3, or a resistor is wrong/shorted.")

for pin in inputs:
    # Averaged over 0.1 s: if a clamp happens to carry current, its AC signal
    # averages out and only the DC level (which should equal the bias) is left.
    level_readings = adc.sample(pin, "GND", 4.096, seconds=0.1)
    level = sum(level_readings) / len(level_readings)
    level_ok = abs(level - bias) < 0.05
    print(f"{verdict(level_ok)} {pin} level: {level:.3f} V (expected same as bias)")
    if not level_ok:
        print(f"      -> clamp not plugged in, wrong wire pair in the cable, or {pin} not wired.")
        print(f"--    {pin} - {BIAS_INPUT} checks skipped: they mean nothing until {pin} is connected.")
        continue

    readings = adc.sample(pin, BIAS_INPUT, FULL_SCALE_V, seconds=1.0)
    mean_mv = sum(readings) / len(readings) * 1000
    noise_a = rms_amps(readings)
    offset_ok = abs(mean_mv) < 5
    noise_ok = noise_a < 0.05
    print(f"{verdict(offset_ok)} {pin} - {BIAS_INPUT} offset: {mean_mv:+.2f} mV (expected ~0)")
    print(f"{verdict(noise_ok)} {pin} noise with no load: {noise_a * 1000:.1f} mA equivalent (expected well under 50 mA)")
