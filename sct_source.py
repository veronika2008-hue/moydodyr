"""
Current-based data source for SCT-013-060 clamp sensors read through ADS1115
ADC boards (Variant B — Raspberry Pi + current sensing). Same interface as
TapoSource (tapo_source.py), so bot.py can use either.

Each clamp sits between the shared 1.65 V bias (wired to A3) and its own
input (A0/A1/A2). The ADC reads the difference, which is the clamp's AC
signal with the bias removed. Current is the RMS of a burst of readings
taken at the ADC's maximum rate (860/s, ~17 readings per 50 Hz period).

Runs on the Raspberry Pi only (talks to the I2C bus through ads1115.py).
"""

import asyncio
import math

from ads1115 import ADS1115
from config import SCT_CHANNELS, SCT_MV_PER_AMP
from cycle_tracker import CycleTracker, washing_before_after_heat_key

BIAS_INPUT = "A3"
FULL_SCALE_V = 0.512    # +/-0.512 V: fits up to ~21 A RMS at 16.67 mV/A
SAMPLE_SECONDS = 0.5    # 25 mains periods per reading

# Current thresholds (A). ESTIMATES converted from the smart-plug calibration
# (tapo_source.py) at ~230 V; motors draw more current than watts/volts
# suggests, so spinning/washing are rounded up. Replace with numbers read off
# a real logged cycle (sct_calibrate.py).
STAGE_THRESHOLDS = {
    "free_max": 0.05,     # idle ~3-4 W -> ~0.02 A
    "heating_min": 4.0,   # heating ~1900 W -> ~8.3 A
    "spinning_min": 0.9,  # spinning ~170-207 W; washing pulses stayed under ~91 W
}

# Typical seconds remaining when a machine first enters each stage. Copied
# from tapo_source.py (same machines, same cycle); re-check against a logged
# current cycle.
STAGE_ENTRY_REMAINING = {
    "washing_before_heat": 1682,
    "heating": 1620,
    "washing_after_heat": 1400,
    "spinning": 433,
}


def classify_stage(amps: float) -> str:
    """Same shape as tapo_source.classify_stage, fed amps instead of watts."""
    if amps < STAGE_THRESHOLDS["free_max"]:
        return "free"
    elif amps >= STAGE_THRESHOLDS["heating_min"]:
        return "heating"
    elif amps >= STAGE_THRESHOLDS["spinning_min"]:
        return "spinning"
    else:
        return "washing"


def rms_amps(readings_v: list[float]) -> float:
    """RMS of the AC part of the clamp signal, converted to amps."""
    mean = sum(readings_v) / len(readings_v)
    rms_v = math.sqrt(sum((v - mean) ** 2 for v in readings_v) / len(readings_v))
    return rms_v * 1000 / SCT_MV_PER_AMP


class SctSource:
    """Polls the clamps listed in config.SCT_CHANNELS and returns statuses in
    the same shape as TapoSource.get_all_statuses()."""

    def __init__(self):
        self._boards = {}  # {i2c_address: ADS1115}
        self._cycles = CycleTracker(
            STAGE_ENTRY_REMAINING,
            key_fn=washing_before_after_heat_key,
            state_file="sct_cycle_state.json",
        )

    def _board(self, address: int) -> ADS1115:
        if address not in self._boards:
            self._boards[address] = ADS1115(address=address)
        return self._boards[address]

    def read_amps_blocking(self, machine_id: str) -> float:
        cfg = SCT_CHANNELS[machine_id]
        readings = self._board(cfg["i2c_address"]).sample(
            cfg["input"], BIAS_INPUT, FULL_SCALE_V, SAMPLE_SECONDS
        )
        return rms_amps(readings)

    async def get_amps(self, machine_id: str) -> float:
        """Current draw in amps for one machine."""
        return await asyncio.to_thread(self.read_amps_blocking, machine_id)

    async def get_all_statuses(self) -> dict[str, dict]:
        """{machine_id: {"stage": str, "remaining_seconds": int | None}}"""
        statuses = {}
        for machine_id in SCT_CHANNELS:
            try:
                amps = await self.get_amps(machine_id)
                stage, remaining = self._cycles.update(machine_id, classify_stage(amps))
                statuses[machine_id] = {"stage": stage, "remaining_seconds": remaining}
            except Exception:
                # Sensor unreadable — mark as unknown instead of crashing the
                # whole bot over one machine.
                statuses[machine_id] = {"stage": "unknown", "remaining_seconds": None}
        return statuses
