"""Select entities for Dangbei Tank."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import DangbeiTankEntity


async def async_setup_entry(hass, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities([DangbeiWaterPumpModeSelect(coordinator, entry)])


class DangbeiWaterPumpModeSelect(DangbeiTankEntity, SelectEntity):
    _attr_options = ["1", "2", "3"]

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "water_pump_mode", "Water Pump Mode")

    @property
    def current_option(self) -> str | None:
        value = self._properties().get("waterPump")
        if value in {1, 2, 3}:
            return str(value)
        return None

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            raise ValueError(f"Unsupported option: {option}")
        await self.coordinator.api.async_send_command(
            self._client_id,
            {"service_name": "setProperty", "items": {"waterPump": int(option)}},
        )
        await self.coordinator.async_request_refresh()
