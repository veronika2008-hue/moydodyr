# Moydodyr — laundry machine status for a dorm

A Telegram bot and a web page that show which of the six washing machines in a
dorm laundry room are free, which are running, what stage each one is in
(washing, heating, spinning), and roughly how long is left — so nobody has to
walk down to check.

The machines themselves have no network connection. The system works out
their state from how much electricity they draw.

## Two hardware approaches

**Variant A — smart plugs (working).** TP-Link Tapo P110 plugs between the
wall and two of the machines report power draw over Wi-Fi. `tapo_source.py`
reads them locally (no cloud round-trip per poll) and classifies the stage
from power: idle ~3–4 W, heating ~1900 W, spinning ~170–210 W, washing in
short motor pulses under ~90 W. Thresholds were calibrated from a real logged
wash cycle (`data/tapo_full_cycle_2026-09-19.csv`).

**Variant B — current clamps on a Raspberry Pi (in progress).** A Raspberry
Pi Zero 2W with an ADS1115 16-bit ADC board reads SCT-013-060 split-core
current transformers clamped around one conductor of each machine's power
lead. One Pi can serve all six machines over wires, with no Wi-Fi needed at
the machines.

## How the current measurement works

- The clamp outputs a small AC voltage (16.7 mV per amp) that swings above
  and below zero; the ADC can only read 0–3.3 V. A 10k/10k divider lifts the
  signal's zero to 1.65 V so the whole wave fits in the ADC's range.
- Each clamp sits between that 1.65 V bias (on A3) and its own input
  (A0/A1/A2). The ADC measures the difference, which removes the bias exactly
  and allows a ±0.512 V range (about 1 mA resolution).
- `sct_source.py` takes 0.5 s of readings at the ADC's maximum 860 samples/s
  (~17 per 50 Hz period) and computes RMS current.

## Notable problems and fixes

- **Tapo power units.** Readings were 1000× too small: the installed `tapo`
  library returns watts, but the code assumed milliwatts. Found by reading the
  library's type stubs after ruling out network and reconnect logic.
- **ADS1115 driver.** The Adafruit library stack (Blinka → lgpio) would not
  build on Raspberry Pi OS (Debian 13), so `ads1115.py` is a small
  register-level driver written from the TI datasheet using `smbus2`. A
  second bug surfaced when two scripts disagreed about the same input: a
  single-shot start request is ignored while the chip is still in continuous
  mode, so the first reading after a burst was stale. Fixed by putting the
  chip into single-shot mode and letting it settle before starting.
- **Bias divider debugging.** The first reading on a breadboard prototype was
  3.27 V instead of 1.65 V: the two resistors were on opposite sides of the
  breadboard's centre channel, which isn't connected. The on-board thermistor
  was also wired to AIN0 through a jumper and had to be disconnected.
- **Time remaining.** Estimated per stage, not as one countdown: each stage
  change resyncs to "time typically left from here" from calibration. The
  fill and the main wash both read as "washing"; cycle history (has heating
  happened yet?) tells them apart.
- **False "free" notifications.** Wash cycles pause with near-zero power, so a
  machine only counts as free after reading free for 2 minutes. A network blip
  ("unknown") never resets the tracked cycle, and the state survives bot
  restarts (`cycle_tracker.py`).
- **Overloaded plugs.** Every open browser tab used to poll the plugs
  directly, and the plugs' small HTTP servers stopped responding. Now one
  background poller talks to the hardware and everything else reads its
  cached result.
- **Wi-Fi.** The school network is WPA2-Enterprise (per-user login). The smart
  plugs and budget routers can't join it; the Raspberry Pi can, which is one
  reason Variant B suits the final setup.

## Status

| | |
|---|---|
| Variant A: plugs, bot, web page, calibration | working |
| Variant B: Pi + ADS1115, driver, bias divider (1.645 V measured) | working |
| SCT-013 noise floor with an empty clamp | 0.013 A |
| First real loads through the clamp (soldering iron, vacuum cleaner) | measured |
| Full washing-machine cycle logged by current | not yet — Variant B thresholds are estimates |
| Pi on the school network, bot running on the Pi | not yet |

## Files

| File | What it does |
|---|---|
| `bot.py` | Telegram bot (`/status`, `/notify`) and the web page / status API on port 8080 |
| `moydodyr-app.html` | Web page with live machine status and browser notifications |
| `tapo_source.py`, `find_tapo_ip.py` | Variant A: read Tapo plugs, find them by MAC when their IP changes |
| `ads1115.py`, `sct_source.py` | Variant B: ADC driver and current-based machine status |
| `cycle_tracker.py` | Shared stage tracking and time-remaining estimate |
| `machines.py` | Machine IDs and status formatting for the bot |
| `calibrate.py`, `sct_calibrate.py` | Log a full wash cycle (power / current) to CSV for calibration |
| `test_tapo.py`, `ads_test.py`, `bias_test.py`, `watch_inputs.py` | Hardware checks and a live view of the ADC inputs |
| `data/` | Logged wash cycles |

## Running it

```bash
pip install -r requirements.txt
cp config.example.py config.py   # then fill in your own values
python bot.py                    # bot + web page at http://localhost:8080/
```

On the Raspberry Pi (Variant B): enable I2C (`sudo raspi-config` → Interface
Options → I2C), create a virtual environment, `pip install smbus2`, then run
`bias_test.py` with the clamp plugged in but not around any cable, and
`watch_inputs.py` for live readings.

## Safety

The measurement side runs at 3.3 V; the clamp is galvanically isolated from
the mains and never touches live conductors. Clamping needs a single
conductor, so a lead with live and neutral separated is used — that part is
mains wiring and was only done with supervision.
