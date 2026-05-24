"""Button entities for Dangbei Tank."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import DangbeiTankEntity


async def async_setup_entry(hass, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities([DangbeiFeedNowButton(coordinator, entry)])


class DangbeiFeedNowButton(DangbeiTankEntity, ButtonEntity):
    """Trigger one immediate feeding action."""

    _attr_icon = "mdi:fish-food"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "feed_now", "Feed Now")

    async def async_press(self) -> None:
        await self.coordinator.api.async_send_command(
            self._client_id,
            {
                "service_name": "feed",
                "items": {"num": 1},
                "request_id": "button_feed_now",
            },
        )
