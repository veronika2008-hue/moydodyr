"""
Shared helper for estimating "time remaining" in a machine's wash cycle
from nothing but its currently classified stage (free/washing/heating/
spinning/...). Used by both tapo_source.py and sct_source.py so the
free->busy transition bookkeeping isn't duplicated between them.

Estimates per-stage, not linearly from cycle start: each time a machine
enters a new stage, the estimate resyncs to "how much time is typically
left once you reach this stage" (from calibration), instead of just
counting down from one fixed total set at the moment the cycle started.
This self-corrects at every observed transition — a cycle running faster
or slower than the calibrated reference doesn't keep drifting the estimate
further off, the way a single up-front total would.
"""

import json
import os
import time

BUSY_STAGES = ("washing", "heating", "spinning")


def washing_before_after_heat_key(stage: str, stages_seen_this_cycle: set) -> str:
    """Default key_fn for sources whose classify_stage() only reports
    "washing" for both the initial fill and the main wash/rinse (they look
    identical from instantaneous power/current alone). Splits them using
    cycle history: the first "washing" is before heating, any "washing"
    seen after "heating" is the main wash/rinse."""
    if stage == "washing":
        return "washing_after_heat" if "heating" in stages_seen_this_cycle else "washing_before_heat"
    return stage


class CycleTracker:
    def __init__(
        self,
        stage_entry_remaining: dict,
        key_fn=None,
        state_file: str = None,
        free_confirm_seconds: float = 120,
    ):
        """
        stage_entry_remaining: {segment_key: seconds_remaining_typically
            left when a machine first enters that segment}, calibrated from
            real data (see each source module for where its numbers come
            from).
        key_fn: (stage, stages_seen_this_cycle) -> segment_key. Lets a
            single classify_stage() label stand for more than one real
            segment — e.g. "washing" covers both the initial fill (before
            heating) and the main wash/rinse (after heating), which have
            very different typical remaining times but look identical from
            instantaneous power alone; cycle history disambiguates them.
            Defaults to using the stage name as-is.
        state_file: optional path to persist tracked state to (as JSON), so
            an in-progress cycle's estimate survives the bot process being
            restarted instead of looking like a fresh cycle. Written after
            every update() call; loaded once on construction.
        free_confirm_seconds: how long a busy machine must read "free"
            before it's believed. Wash cycles pause with almost no power
            draw; a few seconds of that is not the end of the cycle.
        """
        self.stage_entry_remaining = stage_entry_remaining
        self.key_fn = key_fn or (lambda stage, seen: stage)
        self.state_file = state_file
        self.free_confirm_seconds = free_confirm_seconds
        self._last_stage = {}         # {machine_id: last reported stage}
        self._stages_seen = {}        # {machine_id: set of stages seen this cycle}
        self._segment_start = {}      # {machine_id: unix timestamp the current segment began}
        self._segment_remaining = {}  # {machine_id: seconds remaining at entry to the current segment}
        self._free_since = {}         # {machine_id: unix timestamp a busy machine started reading "free"}
        if self.state_file:
            self._load()

    def _load(self):
        if not os.path.exists(self.state_file):
            return
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return
        for machine_id, entry in data.items():
            self._last_stage[machine_id] = entry["last_stage"]
            self._stages_seen[machine_id] = set(entry["stages_seen"])
            if entry["segment_start"] is not None:
                self._segment_start[machine_id] = entry["segment_start"]
                self._segment_remaining[machine_id] = entry["segment_remaining"]
            if entry.get("free_since") is not None:
                self._free_since[machine_id] = entry["free_since"]

    def _save(self):
        if not self.state_file:
            return
        machine_ids = set(self._last_stage) | set(self._stages_seen) | set(self._free_since)
        data = {
            machine_id: {
                "last_stage": self._last_stage.get(machine_id, "free"),
                "stages_seen": sorted(self._stages_seen.get(machine_id, set())),
                "segment_start": self._segment_start.get(machine_id),
                "segment_remaining": self._segment_remaining.get(machine_id),
                "free_since": self._free_since.get(machine_id),
            }
            for machine_id in machine_ids
        }
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except OSError:
            pass

    def _remaining(self, machine_id: str, now: float) -> int | None:
        if machine_id not in self._segment_start:
            return None  # this stage isn't in the calibrated table — no estimate
        elapsed = now - self._segment_start[machine_id]
        return max(0, round(self._segment_remaining[machine_id] - elapsed))

    def update(self, machine_id: str, stage: str) -> tuple[str, int | None]:
        """Call once per poll with the machine's freshly classified stage.
        Returns (stage to report, estimated seconds remaining or None).

        - "unknown" (no reading this poll) leaves the tracked cycle as it is,
          so a network blip mid-cycle doesn't reset the estimate.
        - "free" in the middle of a cycle is only reported once it has lasted
          free_confirm_seconds; until then the previous busy stage is.
        """
        if stage == "unknown":
            return "unknown", None

        now = time.time()
        last_stage = self._last_stage.get(machine_id, "free")

        if stage == "free":
            if last_stage in BUSY_STAGES:
                since = self._free_since.setdefault(machine_id, now)
                if now - since < self.free_confirm_seconds:
                    self._save()
                    return last_stage, self._remaining(machine_id, now)
            self._last_stage[machine_id] = "free"
            self._stages_seen.pop(machine_id, None)
            self._segment_start.pop(machine_id, None)
            self._segment_remaining.pop(machine_id, None)
            self._free_since.pop(machine_id, None)
            self._save()
            return "free", None

        self._free_since.pop(machine_id, None)
        seen = self._stages_seen.setdefault(machine_id, set())
        if stage != last_stage or machine_id not in self._segment_start:
            # Entered a new segment — resync the estimate from calibration.
            key = self.key_fn(stage, seen)
            if key in self.stage_entry_remaining:
                self._segment_start[machine_id] = now
                self._segment_remaining[machine_id] = self.stage_entry_remaining[key]
            seen.add(stage)
        self._last_stage[machine_id] = stage
        self._save()
        return stage, self._remaining(machine_id, now)
