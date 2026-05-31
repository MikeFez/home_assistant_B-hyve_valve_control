"""Valve switch entity."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .ble_device import BhyveBLEDevice, DeviceStatus
from .coordinator import BhyveCoordinator
from .const import CONF_DEFAULT_DURATION, CONF_DEVICE_NAME, DEFAULT_DURATION_SEC, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        BhyveValveSwitch(
            coordinator=data["coordinator"],
            device=data["device"],
            entry=entry,
        )
    ])


class BhyveValveSwitch(CoordinatorEntity[BhyveCoordinator], SwitchEntity):
    _attr_has_entity_name = True
    _attr_name = "Valve"
    _attr_icon = "mdi:water"

    def __init__(
        self,
        coordinator: BhyveCoordinator,
        device: BhyveBLEDevice,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._device = device
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_valve"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_DEVICE_NAME, "B-Hyve Timer"),
            manufacturer="Orbit",
            model="HT31 Hose Tap Timer",
        )

    @property
    def is_on(self) -> bool:
        if self.coordinator.data is None:
            return False
        return self.coordinator.data.watering

    async def async_turn_on(self, **kwargs: Any) -> None:
        duration = self._entry.options.get(CONF_DEFAULT_DURATION, DEFAULT_DURATION_SEC)
        try:
            status = await self._device.start_watering(duration)
            self.coordinator.async_set_updated_data(status)
        except Exception as err:
            _LOGGER.error("Failed to start watering: %s", err)

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            status = await self._device.stop_watering()
            self.coordinator.async_set_updated_data(status)
        except Exception as err:
            _LOGGER.error("Failed to stop watering: %s", err)
