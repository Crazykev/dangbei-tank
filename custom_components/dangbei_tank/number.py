"""Number entities for Dangbei Tank."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import DangbeiTankEntity


async def async_setup_entry(hass, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities([DangbeiFeedPauseTimeNumber(coordinator, entry)])


class DangbeiFeedPauseTimeNumber(DangbeiTankEntity, NumberEntity):
    _attr_native_min_value = 0
    _attr_native_max_value = 3600
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "s"
    _attr_mode = "box"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "feed_pause_time", "Feed Pause Time")

    @property
    def native_value(self):
        return self._properties().get("feedPauseTime")

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.api.async_send_command(
            self._client_id,
            {
                "service_name": "setProperty",
                "items": {
                    "feedingProtectionSwitch": 1,
                    "feedPauseTime": int(round(value)),
                },
            },
        )
        await self.coordinator.async_request_refresh()
