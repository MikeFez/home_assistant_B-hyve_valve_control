"""B-Hyve BLE integration."""
from __future__ import annotations

import base64
import logging
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall


from .ble_device import BhyveBLEDevice
from .coordinator import BhyveCoordinator
from .const import (
    ATTR_DURATION,
    CONF_DEVICE_ID,
    CONF_NETWORK_KEY,
    CONF_POLL_INTERVAL,
    CONF_PROVISION_VER,
    DEFAULT_DURATION_SEC,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MIN_DURATION_SEC,
    SERVICE_START_WATERING,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.BUTTON, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    device = BhyveBLEDevice(
        network_key=base64.b64decode(entry.data[CONF_NETWORK_KEY]),
        device_id=bytes.fromhex(entry.data[CONF_DEVICE_ID]),
        provision_version=entry.data[CONF_PROVISION_VER],
        ble_address=_mac_to_address(entry.data[CONF_DEVICE_ID]),
        hass=hass,
    )

    poll_interval = entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
    coordinator = BhyveCoordinator(hass, device, poll_interval)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "device": device,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _mac_to_address(device_id_hex: str) -> str:
    """Convert hex device_id '446755842f04' to BLE address format."""
    h = device_id_hex.lower().replace(":", "")
    return ":".join(h[i:i+2] for i in range(0, 12, 2)).upper()


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_START_WATERING):
        return

    schema = vol.Schema({
        vol.Optional(ATTR_DURATION, default=DEFAULT_DURATION_SEC): vol.All(
            int, vol.Range(min=MIN_DURATION_SEC, max=14400)
        ),
    })

    async def _handle_start_watering(call: ServiceCall) -> None:
        duration = call.data[ATTR_DURATION]
        for entry_data in hass.data[DOMAIN].values():
            device: BhyveBLEDevice = entry_data["device"]
            coordinator: BhyveCoordinator = entry_data["coordinator"]
            try:
                status = await device.start_watering(duration)
                coordinator.async_set_updated_data(status)
            except Exception as err:
                _LOGGER.error("start_watering failed: %s", err)

    hass.services.async_register(DOMAIN, SERVICE_START_WATERING, _handle_start_watering, schema)
