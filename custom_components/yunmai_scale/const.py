"""Constants for the Yunmai Scale integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "yunmai_scale"
PLATFORMS = [Platform.SENSOR]
PROFILE_SENSOR_KINDS = ("weight", "fat", "impedance", "timestamp")

CONF_DEVICE_NAME = "device_name"
CONF_PROFILES = "profiles"
CONF_PROFILE_NAME = "profile_name"
CONF_UID = "uid"
CONF_HEIGHT_CM = "height_cm"
CONF_SEX = "sex"
CONF_BIRTH_YEAR = "birth_year"
CONF_BIRTH_DATE = "birth_date"  # Legacy v2 profile compatibility only
CONF_AGE = "age"  # Legacy v1 profile compatibility only
CONF_REFERENCE_WEIGHT = "reference_weight"
CONF_ACTIVITY = "activity"
CONF_ADD_ANOTHER = "add_another"

CONF_MAX_RELATIVE_DIFFERENCE = "max_relative_difference"
CONF_MIN_SECOND_BEST_MARGIN_KG = "min_second_best_margin_kg"
CONF_STABLE_FRAMES = "stable_frames"
CONF_MAX_STABLE_SPREAD_KG = "max_stable_spread_kg"
# Legacy v0.3.2 on/off option.
CONF_BLE_POWER_OPTIMIZATION = "ble_power_optimization"
CONF_BLE_POWER_MODE = "ble_power_mode"
CONF_BLE_POWER_INTERVAL_MS = "ble_power_interval_ms"
CONF_BLE_POWER_LATENCY = "ble_power_latency"
CONF_BLE_POWER_SUPERVISION_TIMEOUT_S = "ble_power_supervision_timeout_s"

DEFAULT_MAX_RELATIVE_DIFFERENCE = 0.10
DEFAULT_MIN_SECOND_BEST_MARGIN_KG = 2.0
DEFAULT_STABLE_FRAMES = 3
DEFAULT_MAX_STABLE_SPREAD_KG = 0.8

# Experimental local-BlueZ power optimization. Existing v0.3.2 enabled
# entries migrate in memory to the maximum-tested preset.
DEFAULT_BLE_POWER_OPTIMIZATION = True

BLE_POWER_MODE_OFF = "off"
BLE_POWER_MODE_MODERATE = "moderate"
BLE_POWER_MODE_MAXIMUM = "maximum"
BLE_POWER_MODE_CUSTOM = "custom"
BLE_POWER_MODES = (
    BLE_POWER_MODE_OFF,
    BLE_POWER_MODE_MODERATE,
    BLE_POWER_MODE_MAXIMUM,
    BLE_POWER_MODE_CUSTOM,
)
DEFAULT_BLE_POWER_MODE = BLE_POWER_MODE_MAXIMUM

# Values are controller units: interval 1.25 ms, timeout 10 ms.
BLE_POWER_PRESETS = {
    BLE_POWER_MODE_MODERATE: (36, 9, 1200),   # idle up to 450 ms
    BLE_POWER_MODE_MAXIMUM: (36, 19, 1200),  # idle up to 900 ms
}
DEFAULT_BLE_POWER_INTERVAL_MS = 45.0
DEFAULT_BLE_POWER_LATENCY = 19
DEFAULT_BLE_POWER_SUPERVISION_TIMEOUT_S = 12.0
BLE_POWER_MGMT_TIMEOUT_SECONDS = 5.0

MAX_PROFILES = 8
MIN_HUMAN_WEIGHT_KG = 20.0

# Persistent-connection state machine.
BOOTSTRAP_SETTLE_SECONDS = 0.2
MEASUREMENT_TIMEOUT_SECONDS = 35.0
LIVE_CYCLE_GAP_SECONDS = 3.0
POST_FINAL_GUARD_SECONDS = 3.0
DUPLICATE_FINAL_WINDOW_SECONDS = 5.0
BLE_DEVICE_WAIT_SECONDS = 30.0
RECONNECT_DELAYS_SECONDS = (1.0, 2.0, 5.0, 10.0, 30.0)
FALLBACK_AVAILABILITY_SECONDS = 12.0

SUPPORTED_NAME_PREFIXES = (
    "YUNMAI-SIGNAL",
    "YUNMAI-ISM",
    "YUNMAI-ISC2P",
    "YUNMAI-Scale-3",
    "YUNMAI-ISSE",
)

UUID_FFE4 = "0000ffe4-0000-1000-8000-00805f9b34fb"
UUID_FFE9 = "0000ffe9-0000-1000-8000-00805f9b34fb"
MAGIC_START = bytes((0x0D, 0x05, 0x13, 0x00, 0x16))

STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = "yunmai_scale"
