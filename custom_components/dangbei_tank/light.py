"""Light entities for Dangbei Tank."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import DangbeiTankEntity

LIGHT_EFFECTS = [f"Mode {mode}" for mode in range(10)]
LIGHT_EFFECT_TO_MODE = {effect: mode for mode, effect in enumerate(LIGHT_EFFECTS)}
LIGHT_MODE_TO_EFFECT = {mode: effect for effect, mode in LIGHT_EFFECT_TO_MODE.items()}


def _percent_to_brightness(percent: Any) -> int | None:
    if percent is None:
        return None
    return round(max(0, min(100, float(percent))) * 255 / 100)


def _brightness_to_percent(brightness: int) -> int:
    return round(max(0, min(255, brightness)) * 100 / 255)


async def async_setup_entry(hass, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities([DangbeiAquariumLight(coordinator, entry)])


class DangbeiAquariumLight(DangbeiTankEntity, LightEntity):
    """Main aquarium light with brightness and effect control."""

    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_icon = "mdi:lightbulb-group"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "aquarium_light", "Aquarium Light")

    @property
    def is_on(self) -> bool:
        return self._properties().get("lightSwitch") == 1

    @property
    def color_mode(self) -> ColorMode:
        return ColorMode.BRIGHTNESS

    @property
    def brightness(self) -> int | None:
        return _percent_to_brightness(self._properties().get("lightBrightness"))

    @property
    def effect(self) -> str | None:
        value = self._properties().get("lightMode")
        if isinstance(value, int):
            return LIGHT_MODE_TO_EFFECT.get(value)
        return None

    @property
    def effect_list(self) -> list[str]:
        return LIGHT_EFFECTS

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "light_mode_code": self._properties().get("lightMode"),
            "light_speed": self._properties().get("lightSpeed"),
            "custom_light_brightness": self._properties().get("customLightBrightness"),
            "custom_light_color": self._properties().get("customLightColor"),
        }

    async def async_turn_on(self, **kwargs) -> None:
        items: dict[str, Any] = {"lightSwitch": 1}

        if (brightness := kwargs.get(ATTR_BRIGHTNESS)) is not None:
            items["lightBrightness"] = _brightness_to_percent(brightness)

        if (effect := kwargs.get(ATTR_EFFECT)) is not None:
            if effect not in LIGHT_EFFECT_TO_MODE:
                raise ValueError(f"Unsupported light effect: {effect}")
            items["lightMode"] = LIGHT_EFFECT_TO_MODE[effect]

        await self.coordinator.api.async_send_command(
            self._client_id,
            {"service_name": "setProperty", "items": items},
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.api.async_send_command(
            self._client_id,
            {"service_name": "setProperty", "items": {"lightSwitch": 0}},
        )
        await self.coordinator.async_request_refresh()
