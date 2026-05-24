"""Diagnostics support for Dangbei Tank."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .const import CONF_API_TOKEN, DOMAIN
from .coordinator import DangbeiTankRuntimeData


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    runtime_data: DangbeiTankRuntimeData = entry.runtime_data
    data = await runtime_data.api.async_get_diagnostics(entry.data["client_id"])
    redacted = dict(entry.data)
    if CONF_API_TOKEN in redacted:
        redacted[CONF_API_TOKEN] = "***"
    return {
        "entry": redacted,
        "state": data,
    }
