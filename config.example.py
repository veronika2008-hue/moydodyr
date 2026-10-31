# Copy this file to config.py and fill in your own values.
# config.py holds secrets (bot token, Tapo password) and is git-ignored.

BOT_TOKEN = "123456:replace-with-the-token-from-BotFather"

# --- Settings for TP-Link Tapo smart plugs (Variant A) ---
# Same email/password you use to log into the Tapo app.
TAPO_EMAIL = "you@example.com"
TAPO_PASSWORD = "your-tapo-password"

# Local IP address of each plug on your Wi-Fi network.
# Find it in the Tapo app: open the device -> Device Info -> IP Address.
# Keys are the machine's physical position in the room, left to right
# ("№1".."№6"), not the order the plugs were bought/paired in.
TAPO_DEVICES = {
    # "№3": "192.168.137.80",
}

# MAC addresses of each plug — these stay constant even when the IP above
# changes after a reconnect. When a machine's MAC is listed here,
# find_tapo_ip.py looks up its current IP automatically instead of using
# the (possibly stale) static IP in TAPO_DEVICES.
# Find it in the Tapo app: Device Info -> MAC Address.
TAPO_MACS = {
    # "№3": "AA-BB-CC-DD-EE-FF",
}

# --- Settings for SCT-013 current clamps via ADS1115 (Variant B) ---
# Wiring: the bias divider (1.65 V) goes to A3 on each board, and each clamp
# sits between that bias and its own input A0, A1 or A2. The ADC reads the
# difference (input - A3), so one board serves 3 machines and 6 machines
# need two boards: the first at I2C address 0x48 (the default), the second
# at 0x49 (set with the board's ADDR jumper) so both share the bus.
SCT_CHANNELS = {
    # "№3": {"i2c_address": 0x48, "input": "A0"},
}

# SCT-013-060 (voltage output, built-in burden resistor): 1 V RMS at 60 A,
# i.e. ~16.67 mV RMS per amp. Nominal value from the sensor's rating — check
# it against a load of known wattage (amps = watts / mains volts).
SCT_MV_PER_AMP = 16.67
