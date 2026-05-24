"""Config flow for Dangbei Tank."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import aiohttp_client, selector

from .api import GatewayApiClient, GatewayApiError
from .const import (
    CONF_API_TOKEN,
    CONF_AREA_ID,
    CONF_CLIENT_ID,
    CONF_DISPLAY_NAME,
    CONF_ENTRY_ID,
    CONF_GATEWAY_BASE_URL,
    DEFAULT_NAME,
    DOMAIN,
)


class DangbeiTankConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the guided setup for one Dangbei tank."""

    VERSION = 1

    def __init__(self) -> None:
        self._api_token = ""
        self._base_url = ""
        self._devices: list[dict[str, Any]] = []
        self._reconfigure_entry: config_entries.ConfigEntry | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            self._base_url = user_input[CONF_GATEWAY_BASE_URL].rstrip("/")
            self._api_token = user_input[CONF_API_TOKEN]
            try:
                self._devices = await self._async_fetch_devices(self._base_url, self._api_token)
            except GatewayApiError:
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_device()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_GATEWAY_BASE_URL, default=self._base_url): str,
                    vol.Required(CONF_API_TOKEN, default=self._api_token): str,
                }
            ),
            errors=errors,
        )

    async def async_step_device(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            client_id = user_input[CONF_CLIENT_ID]
            display_name = user_input[CONF_DISPLAY_NAME].strip() or DEFAULT_NAME
            if self._reconfigure_entry is None:
                await self.async_set_unique_id(client_id)
                self._abort_if_unique_id_configured()
            data = {
                CONF_GATEWAY_BASE_URL: self._base_url,
                CONF_API_TOKEN: self._api_token,
                CONF_CLIENT_ID: client_id,
                CONF_DISPLAY_NAME: display_name,
                CONF_AREA_ID: user_input.get(CONF_AREA_ID, ""),
            }
            if self._reconfigure_entry is not None:
                self.hass.config_entries.async_update_entry(
                    self._reconfigure_entry,
                    data=data,
                    title=display_name,
                )
                await self.hass.config_entries.async_reload(self._reconfigure_entry.entry_id)
                return self.async_abort(reason="reconfigure_successful")
            return self.async_create_entry(title=display_name, data=data)

        options = {
            item["client_id"]: item.get("display_name") or item["client_id"]
            for item in self._devices
        }
        suggested_name = DEFAULT_NAME
        if len(self._devices) == 1:
            suggested_name = self._devices[0].get("display_name") or DEFAULT_NAME
        if self._reconfigure_entry is not None:
            suggested_name = str(self._reconfigure_entry.data.get(CONF_DISPLAY_NAME, suggested_name))
        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CLIENT_ID,
                        default=self._reconfigure_entry.data.get(CONF_CLIENT_ID) if self._reconfigure_entry else next(iter(options)),
                    ): vol.In(options),
                    vol.Required(CONF_DISPLAY_NAME, default=suggested_name): str,
                    vol.Optional(
                        CONF_AREA_ID,
                        default=self._reconfigure_entry.data.get(CONF_AREA_ID, "") if self._reconfigure_entry else "",
                    ): selector.AreaSelector(),
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: Mapping[str, Any] | None = None):
        self._reconfigure_entry = self._get_reconfigure_entry()
        self._base_url = str(self._reconfigure_entry.data[CONF_GATEWAY_BASE_URL])
        self._api_token = str(self._reconfigure_entry.data[CONF_API_TOKEN])
        if not self._devices:
            self._devices = await self._async_fetch_devices(self._base_url, self._api_token)
        return await self.async_step_user(dict(user_input) if user_input else None)

    async def _async_fetch_devices(self, base_url: str, api_token: str) -> list[dict[str, Any]]:
        session = aiohttp_client.async_get_clientsession(self.hass)
        api = GatewayApiClient(session, base_url, api_token)
        return await api.async_get_devices()
