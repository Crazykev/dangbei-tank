"""Shared entity helpers for Dangbei Tank."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_AREA_ID, CONF_CLIENT_ID, CONF_DISPLAY_NAME, DOMAIN
from .coordinator import DangbeiTankCoordinator


class DangbeiTankEntity(CoordinatorEntity[DangbeiTankCoordinator]):
    """Base entity bound to one fish tank coordinator."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DangbeiTankCoordinator, entry: ConfigEntry, key: str, name: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._client_id = str(entry.data[CONF_CLIENT_ID])
        self._display_name = str(entry.data[CONF_DISPLAY_NAME])
        self._key = key
        self._attr_unique_id = f"{self._client_id}_{key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._client_id)},
            manufacturer="Dangbei",
            model="Fish Tank",
            name=self._display_name,
            sw_version=self._identity().get("rom_ver_code"),
        )

    async def async_added_to_hass(self) -> None:
        """Assign the configured area when the entity is added."""
        await super().async_added_to_hass()
        area_id = self._entry.data.get(CONF_AREA_ID)
        if not area_id:
            return
        device_registry = dr.async_get(self.hass)
        device = device_registry.async_get_device(identifiers={(DOMAIN, self._client_id)})
        if device and device.area_id != area_id:
            device_registry.async_update_device(device.id, area_id=area_id)

    def _state(self) -> dict[str, Any]:
        return self.coordinator.data or {}

    def _identity(self) -> dict[str, Any]:
        return self._state().get("identity", {})

    def _properties(self) -> dict[str, Any]:
        return self._state().get("properties", {})

    def _connectivity(self) -> dict[str, Any]:
        return self._state().get("connectivity", {})

    @property
    def available(self) -> bool:
        connectivity = self._connectivity()
        return bool(connectivity.get("broker_connected")) and bool(connectivity.get("device_connected"))
