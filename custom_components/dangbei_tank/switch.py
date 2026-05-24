"""Switch entities for Dangbei Tank."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import DangbeiTankEntity


async def async_setup_entry(hass, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            DangbeiPropertySwitch(coordinator, entry, "power", "Power", "powerSwitch"),
            DangbeiPropertySwitch(coordinator, entry, "feeding_protection", "Feeding Protection", "feedingProtectionSwitch"),
            DangbeiPropertySwitch(coordinator, entry, "accessory_1", "Accessory 1", "peripheralPowerSwitch_1"),
            DangbeiPropertySwitch(coordinator, entry, "accessory_2", "Accessory 2", "peripheralPowerSwitch_2"),
        ]
    )


class DangbeiPropertySwitch(DangbeiTankEntity, SwitchEntity):
    def __init__(self, coordinator, entry: ConfigEntry, key: str, name: str, property_key: str) -> None:
        super().__init__(coordinator, entry, key, name)
        self._property_key = property_key

    @property
    def is_on(self):
        return self._properties().get(self._property_key) == 1

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.api.async_send_command(
            self._client_id,
            {"service_name": "setProperty", "items": {self._property_key: 1}},
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.api.async_send_command(
            self._client_id,
            {"service_name": "setProperty", "items": {self._property_key: 0}},
        )
        await self.coordinator.async_request_refresh()
