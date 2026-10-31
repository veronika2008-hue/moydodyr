"""
Live view of the ADS1115 inputs, one line per second, until Ctrl+C.
Shows each input's voltage against ground (averaged over 0.1 s, so the
clamp's AC signal averages out and only the DC level is left) and the clamp
current measured as A0 - A3 (the bias on A3 subtracted out).

Usage (on the Pi):  ~/moydodyr/venv/bin/python watch_inputs.py
From the laptop:    ssh veronika@<pi address> "cd ~/moydodyr && ./venv/bin/python watch_inputs.py"
"""

import time

from ads1115 import ADS1115
from sct_source import BIAS_INPUT, FULL_SCALE_V, rms_amps

adc = ADS1115()


def mean_voltage(pin: str) -> float:
    readings = adc.sample(pin, "GND", 4.096, seconds=0.1)
    return sum(readings) / len(readings)


print("time       A0       A1       A2       A3      clamp on A0", flush=True)
try:
    while True:
        volts = [mean_voltage(pin) for pin in ("A0", "A1", "A2", "A3")]
        cells = "  ".join(f"{v:6.3f} V" for v in volts)
        # A clamp ties A0 to the bias, so on average A0 sits at the bias even
        # while current flows. Far from it means nothing is connected, and
        # any "current" would just be a floating pin's noise.
        if abs(volts[0] - volts[3]) < 0.1:
            amps = rms_amps(adc.sample("A0", BIAS_INPUT, FULL_SCALE_V, seconds=0.5))
            clamp = f"{amps:6.3f} A"
        else:
            clamp = "  not connected"
            time.sleep(0.5)
        print(f"{time.strftime('%H:%M:%S')}  {cells}   {clamp}", flush=True)
except KeyboardInterrupt:
    pass
