"""DataUpdateCoordinator for b-hyve BLE battery/status polling."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .ble_device import BhyveBLEDevice, DeviceStatus
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class BhyveCoordinator(DataUpdateCoordinator[DeviceStatus]):
    def __init__(
        self,
        hass: HomeAssistant,
        device: BhyveBLEDevice,
        poll_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval),
        )
        self.device = device
        self.last_seen: datetime | None = None

    async def _async_update_data(self) -> DeviceStatus:
        try:
            result = await self.device.poll_status()
            self.last_seen = datetime.now(timezone.utc)
            return result
        except Exception as err:
            raise UpdateFailed(f"BLE poll failed: {err}") from err
