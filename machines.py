"""
Simulation of machine states over time.
Each machine cycles through: free -> washing -> rinsing -> spinning -> free -> ...
Durations are compressed (seconds instead of minutes) so the bot can be tested
in a couple of minutes instead of waiting for a real 30-90 minute wash cycle.

Once real hardware is connected (smart plug / SCT-013+ADS1115), the tick()
function will be replaced by an actual device poll + power-based
classification instead of a timer.
"""

import random

MACHINE_IDS = [f"№{i}" for i in range(1, 7)]

STAGE_FLOW = ["washing", "rinsing", "spinning"]  # stage order after "free"

# Compressed demo durations (seconds). Will be replaced by real cycle timing.
STAGE_DURATION_RANGE = {
    "washing": (25, 40),
    "rinsing": (15, 25),
    "spinning": (15, 25),
    "free": (20, 60),  # how long it stays free before someone starts a wash
}

ICONS = {
    "free": "🟢",
    "washing": "🔵",
    "rinsing": "🔵",
    "heating": "🔴",
    "spinning": "🟠",
}


def _new_duration(stage: str) -> int:
    lo, hi = STAGE_DURATION_RANGE[stage]
    return random.randint(lo, hi)


def _init_state() -> dict:
    state = {}
    for mid in MACHINE_IDS:
        stage = random.choice(["free"] + STAGE_FLOW)
        state[mid] = {"stage": stage, "remaining": _new_duration(stage)}
    return state


_state = _init_state()


def get_all_statuses() -> dict[str, dict]:
    """Current status of all machines (does not change state).
    {machine_id: {"stage": str, "remaining_seconds": int}}"""
    return {
        mid: {"stage": info["stage"], "remaining_seconds": info["remaining"]}
        for mid, info in _state.items()
    }


def fmt_time(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds == 0:
        return "0 min"
    return f"{max(1, round(seconds / 60))} min"


def format_status_line(machine_id: str, info: dict) -> str:
    stage = info["stage"]
    icon = ICONS.get(stage, "⚪")
    remaining = info.get("remaining_seconds")
    if stage == "free" or remaining is None:
        return f"{icon} {machine_id} — {stage}"
    return f"{icon} {machine_id} — {stage} (~{fmt_time(remaining)} left)"


def tick(seconds: int = 5) -> list[str]:
    """
    Advances the simulation by `seconds`.
    Returns the list of machine ids that JUST became free
    (needed to notify subscribers).
    """
    just_freed = []
    for mid, info in _state.items():
        info["remaining"] -= seconds
        if info["remaining"] <= 0:
            current = info["stage"]
            if current == "free":
                next_stage = "washing"
            else:
                idx = STAGE_FLOW.index(current)
                if idx + 1 < len(STAGE_FLOW):
                    next_stage = STAGE_FLOW[idx + 1]
                else:
                    next_stage = "free"
                    just_freed.append(mid)
            info["stage"] = next_stage
            info["remaining"] = _new_duration(next_stage)
    return just_freed
