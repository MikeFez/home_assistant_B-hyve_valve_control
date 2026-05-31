DOMAIN = "bhyve_ble"

# GATT UUIDs
AES_CHAR_UUID     = "00006c71-fe32-4f58-8b78-98e42b2c047f"
WRITE_CHAR_UUID   = "00006c72-fe32-4f58-8b78-98e42b2c047f"
READ_CHAR_UUID    = "00006c73-fe32-4f58-8b78-98e42b2c047f"
NETWORK_CHAR_UUID = "00006c76-fe32-4f58-8b78-98e42b2c047f"

BHYVE_MFR_ID     = 0x047F
MESSAGE_FLAG     = 0x11   # device silently ignores commands with flag=0x00
MIN_DURATION_SEC = 15     # device-enforced minimum

# Orbit API
ORBIT_API_BASE = "https://api.orbitbhyve.com/v1"

# Config entry keys
CONF_NETWORK_KEY      = "network_key"
CONF_DEVICE_ID        = "device_id"
CONF_PROVISION_VER    = "provision_version"
CONF_DEVICE_NAME      = "device_name"

# Options
CONF_POLL_INTERVAL    = "poll_interval"
CONF_DEFAULT_DURATION = "default_duration"

DEFAULT_POLL_INTERVAL    = 3600   # seconds (1 hour)
DEFAULT_DURATION_SEC     = 300    # 5 minutes

# Services
SERVICE_START_WATERING = "start_watering"
ATTR_DURATION          = "duration"
