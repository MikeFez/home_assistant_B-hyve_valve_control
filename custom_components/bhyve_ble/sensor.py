"""Sensor entities."""
from __future__ import annotations

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import BhyveCoordinator
from .const import CONF_DEVICE_NAME, DOMAIN

# Empirical voltage range for the HT31 (single LiFePO4 cell or voltage-divided 4xAA).
# Adjust BATTERY_MAX_MV / BATTERY_MIN_MV if the percentage looks wrong for your device.
# Testing showed ~3186 mV with "fresh" batteries — calibrate by checking reported mV at full/empty.
BATTERY_MAX_MV = 3200   # 100 %
BATTERY_MIN_MV = 2400   # 0 %


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        BhyveBatterySensor(coordinator=data["coordinator"], entry=entry),
        BhyveLastSeenSensor(coordinator=data["coordinator"], entry=entry),
    ])


class BhyveBatterySensor(CoordinatorEntity[BhyveCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:battery"

    def __init__(self, coordinator: BhyveCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_battery"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_DEVICE_NAME, "B-Hyve Timer"),
            manufacturer="Orbit",
            model="HT31 Hose Tap Timer",
        )

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None or self.coordinator.data.battery_mv is None:
            return None
        mv = self.coordinator.data.battery_mv
        pct = (mv - BATTERY_MIN_MV) / (BATTERY_MAX_MV - BATTERY_MIN_MV) * 100
        return max(0, min(100, round(pct)))

    @property
    def extra_state_attributes(self) -> dict:
        if self.coordinator.data and self.coordinator.data.battery_mv is not None:
            return {"battery_mv": self.coordinator.data.battery_mv}
        return {}


class BhyveLastSeenSensor(CoordinatorEntity[BhyveCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Last Seen"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:bluetooth-connect"

    def __init__(self, coordinator: BhyveCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_last_seen"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_DEVICE_NAME, "B-Hyve Timer"),
            manufacturer="Orbit",
            model="HT31 Hose Tap Timer",
        )

    @property
    def native_value(self) -> datetime | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.last_seen
