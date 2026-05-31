# B-Hyve BLE — Home Assistant Custom Component

Local Bluetooth control of Orbit B-Hyve hose tap timers — no WiFi hub or cloud required.

Confirmed working on: `HT31-0001` (Smart Hose Tap Timer)

## Installation via HACS

1. In HACS → Integrations → ⋮ → Custom repositories
2. Add this repo URL, category **Integration**
3. Install **B-Hyve BLE**
4. Restart Home Assistant

## Setup

1. Settings → Devices & Services → Add Integration → **B-Hyve BLE**
2. Enter your Orbit account email and password
3. The integration auto-fetches your device credentials from the Orbit API

## Entities

| Entity | Type | Description |
|--------|------|-------------|
| `switch.bhyve_ble_valve` | Switch | ON = start watering (default duration), OFF = stop |
| `sensor.bhyve_ble_battery` | Sensor | Battery % (polled via BLE on configurable interval) |

## Action: `bhyve_ble.start_watering`

Start watering for a specific duration:

```yaml
action: bhyve_ble.start_watering
target:
  entity_id: switch.bhyve_ble_valve
data:
  duration: 120   # seconds, minimum 15
```

## Options

After setup, configure via the integration's **Configure** button:

- **Default watering duration** — used when the switch is turned on (default: 300s / 5 min)
- **Battery poll interval** — how often to connect via BLE to read battery (default: 3600s / 1 hr)

## Battery Calibration

The battery percentage is derived from the raw mV reading in BLE notifications.
Default calibration: 3200 mV = 100%, 2400 mV = 0%. If the percentage looks wrong,
adjust `BATTERY_MAX_MV` / `BATTERY_MIN_MV` in `sensor.py` to match your device's
actual voltage range.

## Notes

- Each operation (start, stop, battery poll) opens a fresh BLE connection and closes it
- The device requires a minimum 15-second watering duration
- The Mac running HA needs Bluetooth hardware accessible to the HA process
