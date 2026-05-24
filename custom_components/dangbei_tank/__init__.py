"""Home Assistant setup for Dangbei Tank."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import entity_registry as er

from .api import GatewayApiClient, GatewayApiError
from .const import (
    CONF_API_TOKEN,
    CONF_CLIENT_ID,
    CONF_ENTRY_ID,
    CONF_GATEWAY_BASE_URL,
    DOMAIN,
    PLATFORMS,
    SERVICE_DUMP_LAST_RAW_PAYLOADS,
    SERVICE_REFRESH_STATE,
    SERVICE_SEND_RAW_COMMAND,
)
from .coordinator import DangbeiTankCoordinator, DangbeiTankRuntimeData

LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration from one config entry."""
    session = async_get_clientsession(hass)
    api = GatewayApiClient(
        session,
        str(entry.data[CONF_GATEWAY_BASE_URL]),
        str(entry.data[CONF_API_TOKEN]),
    )
    coordinator = DangbeiTankCoordinator(
        hass,
        api=api,
        client_id=str(entry.data[CONF_CLIENT_ID]),
    )
    try:
        await coordinator.async_start()
    except GatewayApiError as err:
        raise ConfigEntryNotReady(str(err)) from err
    except Exception as err:
        raise ConfigEntryNotReady(str(err)) from err

    hass.data.setdefault(DOMAIN, {})
    entry.runtime_data = DangbeiTankRuntimeData(api=api, coordinator=coordinator)
    hass.data[DOMAIN][entry.entry_id] = entry.runtime_data

    await _async_cleanup_obsolete_entities(hass, entry)
    await _async_register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload one config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        runtime_data: DangbeiTankRuntimeData = entry.runtime_data
        await runtime_data.coordinator.async_stop()
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok


async def _async_register_services(hass: HomeAssistant) -> None:
    if hass.data[DOMAIN].get("services_registered"):
        return

    async def refresh_state(call: ServiceCall) -> None:
        entries = _target_entries(hass, call)
        for entry in entries:
            runtime_data: DangbeiTankRuntimeData = entry.runtime_data
            await runtime_data.api.async_refresh_state(entry.data[CONF_CLIENT_ID])
            await runtime_data.coordinator.async_request_refresh()

    async def send_raw_command(call: ServiceCall) -> None:
        entry = _target_entries(hass, call)[0]
        runtime_data: DangbeiTankRuntimeData = entry.runtime_data
        await runtime_data.api.async_send_command(
            entry.data[CONF_CLIENT_ID],
            {
                "topic": call.data["topic"],
                "payload": call.data["payload"],
                "request_id": call.data.get("request_id"),
            },
        )
        await runtime_data.coordinator.async_request_refresh()

    async def dump_last_raw_payloads(call: ServiceCall) -> dict[str, Any]:
        entry = _target_entries(hass, call)[0]
        runtime_data: DangbeiTankRuntimeData = entry.runtime_data
        diagnostics = await runtime_data.api.async_get_diagnostics(entry.data[CONF_CLIENT_ID])
        return diagnostics.get("raw", {})

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_STATE,
        refresh_state,
        schema=vol.Schema({vol.Optional(CONF_ENTRY_ID): str}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_RAW_COMMAND,
        send_raw_command,
        schema=vol.Schema(
            {
                vol.Required(CONF_ENTRY_ID): str,
                vol.Required("topic"): str,
                vol.Required("payload"): str,
                vol.Optional("request_id"): str,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DUMP_LAST_RAW_PAYLOADS,
        dump_last_raw_payloads,
        schema=vol.Schema({vol.Required(CONF_ENTRY_ID): str}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.data[DOMAIN]["services_registered"] = True


def _target_entries(hass: HomeAssistant, call: ServiceCall) -> list[ConfigEntry]:
    entry_id = call.data.get(CONF_ENTRY_ID)
    if entry_id:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ValueError(f"Unknown Dangbei Tank entry_id: {entry_id}")
        return [entry]

    return [entry for entry in hass.config_entries.async_entries(DOMAIN)]


async def _async_cleanup_obsolete_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    entity_registry = er.async_get(hass)
    client_id = str(entry.data[CONF_CLIENT_ID])
    obsolete_unique_ids = {
        f"{client_id}_aquarium_light",
        f"{client_id}_custom_light_brightness",
        f"{client_id}_light",
    }
    for registry_entry in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
        if registry_entry.unique_id in obsolete_unique_ids:
            entity_registry.async_remove(registry_entry.entity_id)
