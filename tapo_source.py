"""
Power data source for TP-Link Tapo smart plugs (P110/P115).

Uses the `tapo` library (pip install tapo) — supports the current KLAP
authentication protocol required by recent Tapo firmware. Works locally
over your Wi-Fi network, without hitting the cloud on every poll (only
needs your Tapo account email/password for the initial handshake).

Once the plugs are set up and connected to Wi-Fi (via the Tapo app), fill
in the email/password and IP addresses in config.py, and this module can
be plugged into bot.py instead of the machines.tick() simulation.
"""

import asyncio

from tapo import ApiClient
from config import TAPO_EMAIL, TAPO_PASSWORD, TAPO_DEVICES
from find_tapo_ip import resolve_ip
from cycle_tracker import CycleTracker, washing_before_after_heat_key

# Typical seconds remaining when a machine FIRST enters each stage,
# calibrated from ONE real "Classic delicate" cycle on machine №1
# (2026-09-19, calibration_n1_20260919_115042.csv; total cycle ~1682s
# including the drain tail). "washing" happens twice in a real cycle —
# filling (before heating) and the main wash/rinse (after heating) — which
# look identical from instantaneous power alone but have very different
# typical remaining time, so cycle history (has "heating" been seen yet?)
# disambiguates them; see tapo_stage_key() below.
#
#   entered at 0s    (fill, before heating): ~1682s left
#   entered at 62s   (heating):              ~1620s left
#   entered at 282s  (main wash/rinse):      ~1400s left
#   entered at 1249s (spinning):             ~433s left
#
# Still an estimate, not a real countdown — a different wash program, or a
# different machine, will run for different real durations. Re-syncing at
# each observed stage transition (see cycle_tracker.py) makes it more
# robust to a cycle running faster/slower than this reference than a
# single linear countdown would be, but it can't fully close that gap.
STAGE_ENTRY_REMAINING = {
    "washing_before_heat": 1682,
    "heating": 1620,
    "washing_after_heat": 1400,
    "spinning": 433,
}

# Power thresholds (W), calibrated from a real "Classic delicate" cycle on
# machine №1 (2026-09-19, see calibration_n1_20260919_115042.csv):
#   - free/idle:     ~3-4 W
#   - filling:       pulses 6-34 W
#   - heating:       stable plateau ~1830-1920 W (62s-278s in the log)
#   - washing/rinse: pulses 4-91 W
#   - spinning:      ramps up to a stable ~170-207 W (1249s-1483s in the log)
STAGE_THRESHOLDS = {
    "free_max": 5,         # below this — the machine draws basically nothing, it's free
    "heating_min": 900,    # well below the observed ~1830W heating plateau
    "spinning_min": 120,   # above the highest observed washing/rinsing pulse (~91W)
}


def classify_stage(watts: float) -> str:
    """
    Rough classification of the cycle stage from instantaneous power.
    Thresholds are placeholders — will need calibration on real wash data.
    """
    if watts < STAGE_THRESHOLDS["free_max"]:
        return "free"
    elif watts >= STAGE_THRESHOLDS["heating_min"]:
        return "heating"
    elif watts >= STAGE_THRESHOLDS["spinning_min"]:
        return "spinning"
    else:
        return "washing"


class TapoSource:
    """Polls Tapo plugs and returns statuses in the same format as
    machines.get_all_statuses() — so this class can be swapped in for the
    simulation without changing bot.py."""

    def __init__(self):
        self.client = ApiClient(TAPO_EMAIL, TAPO_PASSWORD)
        self._devices = {}  # connection cache, so we don't log in every time
        self._cycles = CycleTracker(
            STAGE_ENTRY_REMAINING,
            key_fn=washing_before_after_heat_key,
            state_file="tapo_cycle_state.json",
        )

    async def _get_device(self, machine_id: str, force_refresh: bool = False):
        if force_refresh or machine_id not in self._devices:
            ip = await asyncio.to_thread(resolve_ip, machine_id)
            self._devices[machine_id] = await self.client.p110(ip)
        return self._devices[machine_id]

    async def get_power(self, machine_id: str) -> float:
        """Current power draw in watts for one machine."""
        try:
            device = await self._get_device(machine_id)
            info = await device.get_current_power()
        except Exception:
            # Stale IP/session (plug reconnected to Wi-Fi, got a new
            # address) — re-resolve and retry once before giving up.
            device = await self._get_device(machine_id, force_refresh=True)
            info = await device.get_current_power()
        return info.current_power

    async def get_all_statuses(self) -> dict[str, dict]:
        """Polls every plug listed in config.TAPO_DEVICES.
        {machine_id: {"stage": str, "remaining_seconds": int | None}}"""
        statuses = {}
        for machine_id in TAPO_DEVICES:
            try:
                watts = await self.get_power(machine_id)
                stage, remaining = self._cycles.update(machine_id, classify_stage(watts))
                statuses[machine_id] = {"stage": stage, "remaining_seconds": remaining}
            except Exception:
                # Plug unreachable (off, no network, etc.) — mark as unknown
                # instead of crashing the whole bot over one machine.
                statuses[machine_id] = {"stage": "unknown", "remaining_seconds": None}
        return statuses
