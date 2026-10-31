"""
Minimal ADS1115 driver over I2C, written from the TI datasheet register map.

Used instead of adafruit-circuitpython-ads1x15: its dependency chain
(Adafruit-Blinka -> lgpio) fails to build on Raspberry Pi OS (Debian 13).
smbus2 is pure Python, and talking to the registers directly gives exact
control over input pair, gain and data rate.
"""

import time

from smbus2 import SMBus

REG_CONVERSION = 0x00
REG_CONFIG = 0x01

# (positive input, negative input) -> MUX bits [14:12]
MUX = {
    ("A0", "A1"): 0b000,
    ("A0", "A3"): 0b001,
    ("A1", "A3"): 0b010,
    ("A2", "A3"): 0b011,
    ("A0", "GND"): 0b100,
    ("A1", "GND"): 0b101,
    ("A2", "GND"): 0b110,
    ("A3", "GND"): 0b111,
}
# full-scale range in volts (+/-) -> PGA bits [11:9]
FULL_SCALE = {6.144: 0b000, 4.096: 0b001, 2.048: 0b010, 1.024: 0b011, 0.512: 0b100, 0.256: 0b101}
# samples per second -> DR bits [7:5]
DATA_RATE = {8: 0b000, 16: 0b001, 32: 0b010, 64: 0b011, 128: 0b100, 250: 0b101, 475: 0b110, 860: 0b111}

COMPARATOR_OFF = 0b11  # COMP_QUE bits [1:0]


class ADS1115:
    def __init__(self, bus: int = 1, address: int = 0x48):
        self.address = address
        self.bus = SMBus(bus)
        self.full_scale = 4.096

    def _write_config(self, pos, neg, full_scale, data_rate, single_shot, start=None):
        """single_shot selects the mode; start sets the OS bit (start a
        single conversion), which defaults to on in single-shot mode."""
        if start is None:
            start = single_shot
        cfg = (
            (1 << 15 if start else 0)
            | MUX[(pos, neg)] << 12
            | FULL_SCALE[full_scale] << 9
            | (1 << 8 if single_shot else 0)
            | DATA_RATE[data_rate] << 5
            | COMPARATOR_OFF
        )
        self.bus.write_i2c_block_data(self.address, REG_CONFIG, [cfg >> 8, cfg & 0xFF])
        self.full_scale = full_scale

    def _read_raw(self) -> int:
        hi, lo = self.bus.read_i2c_block_data(self.address, REG_CONVERSION, 2)
        raw = (hi << 8) | lo
        return raw - (1 << 16) if raw & 0x8000 else raw

    def _to_volts(self, raw: int) -> float:
        return raw * self.full_scale / 32768

    def read_voltage(self, pos="A0", neg="GND", full_scale=4.096) -> float:
        """One single-shot conversion. Returns volts (signed for differential pairs)."""
        # A start request (OS=1) is ignored while the chip is still running in
        # continuous mode (after sample()), and the old result would be read
        # back. So first drop to single-shot mode without starting, let any
        # running conversion finish, then start the real one.
        self._write_config(pos, neg, full_scale, 860, single_shot=True, start=False)
        time.sleep(0.003)
        self._write_config(pos, neg, full_scale, 860, single_shot=True)
        time.sleep(0.0015)
        deadline = time.monotonic() + 0.05
        while time.monotonic() < deadline:
            hi, _ = self.bus.read_i2c_block_data(self.address, REG_CONFIG, 2)
            if hi & 0x80:  # OS bit reads 1 once the conversion is done
                break
            time.sleep(0.0005)
        return self._to_volts(self._read_raw())

    def sample(self, pos, neg, full_scale, seconds, data_rate=860) -> list[float]:
        """Continuous mode: one reading per conversion period for `seconds`.
        Returns the readings in volts."""
        self._write_config(pos, neg, full_scale, data_rate, single_shot=False)
        period = 1 / data_rate
        time.sleep(2 * period)  # let the first conversion with the new settings finish
        readings = []
        next_t = time.perf_counter()
        end = next_t + seconds
        while next_t < end:
            readings.append(self._to_volts(self._read_raw()))
            next_t += period
            delay = next_t - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
        return readings
