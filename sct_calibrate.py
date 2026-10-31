"""
Logs current from one SCT-013 clamp to a CSV file for a whole wash cycle,
to calibrate STAGE_THRESHOLDS and STAGE_ENTRY_REMAINING in sct_source.py —
the current-sensing twin of calibrate.py.

Start it right before starting the wash, leave it running, stop it with
Ctrl+C once the machine is done.

Usage (on the Pi):  ~/moydodyr/venv/bin/python sct_calibrate.py [input]
input is the clamp's ADS1115 pin, A0 by default.
"""

import csv
import sys
import time
from datetime import datetime

from ads1115 import ADS1115
from sct_source import BIAS_INPUT, FULL_SCALE_V, SAMPLE_SECONDS, classify_stage, rms_amps

INTERVAL_SECONDS = 2
MAINS_VOLTS = 230  # only for the rough watts column

pin = sys.argv[1] if len(sys.argv) > 1 else "A0"
adc = ADS1115()
log_name = f"sct_calibration_{pin}_{datetime.now():%Y%m%d_%H%M%S}.csv"
print(f"Logging current on {pin} to {log_name}. Start the wash now; Ctrl+C to stop.\n")

start = time.monotonic()
with open(log_name, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["elapsed_seconds", "timestamp", "amps", "watts_estimate", "stage_guess"])
    try:
        while True:
            t0 = time.monotonic()
            amps = rms_amps(adc.sample(pin, BIAS_INPUT, FULL_SCALE_V, SAMPLE_SECONDS))
            elapsed = int(t0 - start)
            stage = classify_stage(amps)
            writer.writerow([elapsed, datetime.now().isoformat(timespec="seconds"), f"{amps:.3f}", round(amps * MAINS_VOLTS), stage])
            f.flush()
            print(f"  {elapsed:>5}s  {amps:6.3f} A  ~{amps * MAINS_VOLTS:5.0f} W  {stage}")
            time.sleep(max(0.0, INTERVAL_SECONDS - (time.monotonic() - t0)))
    except KeyboardInterrupt:
        print(f"\nStopped. Log saved to {log_name}")
