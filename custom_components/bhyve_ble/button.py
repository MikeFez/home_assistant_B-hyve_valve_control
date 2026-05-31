"""Stop watering button entity."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .ble_device import BhyveBLEDevice
from .const import CONF_DEVICE_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BhyveStopButton(device=data["device"], entry=entry)])


class BhyveStopButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Stop Watering"
    _attr_icon = "mdi:stop"

    def __init__(self, device: BhyveBLEDevice, entry: ConfigEntry) -> None:
        self._device = device
        self._attr_unique_id = f"{entry.entry_id}_stop"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_DEVICE_NAME, "B-Hyve Timer"),
            manufacturer="Orbit",
            model="HT31 Hose Tap Timer",
        )

    async def async_press(self) -> None:
        try:
            await self._device.stop_watering()
        except Exception as err:
            _LOGGER.error("Failed to stop watering: %s", err)
