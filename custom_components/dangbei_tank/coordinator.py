"""Coordinator and runtime data for Dangbei Tank."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
from typing import Any

from aiohttp import WSMsgType

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GatewayApiClient, GatewayApiError

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class DangbeiTankRuntimeData:
    """Runtime objects attached to the config entry."""

    api: GatewayApiClient
    coordinator: "DangbeiTankCoordinator"


class DangbeiTankCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate gateway state with fallback polling and a WebSocket push stream."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        api: GatewayApiClient,
        client_id: str,
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            name=f"Dangbei Tank {client_id}",
            update_interval=__import__("datetime").timedelta(seconds=60),
        )
        self.api = api
        self.client_id = client_id
        self._ws_task: asyncio.Task[None] | None = None
        self._ws_stop = asyncio.Event()

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.api.async_get_state(self.client_id)
        except GatewayApiError as err:
            raise UpdateFailed(str(err)) from err

    async def async_start(self) -> None:
        """Fetch the initial state and start the WebSocket listener."""
        await self.async_config_entry_first_refresh()
        self._ws_stop.clear()
        self._ws_task = self.hass.async_create_background_task(
            self._async_ws_loop(),
            name=f"dangbei_tank_ws_{self.client_id}",
        )

    async def async_stop(self) -> None:
        """Stop the WebSocket listener."""
        self._ws_stop.set()
        if self._ws_task is not None:
            self._ws_task.cancel()
            await asyncio.gather(self._ws_task, return_exceptions=True)
            self._ws_task = None

    async def _async_ws_loop(self) -> None:
        backoff = 1
        while not self._ws_stop.is_set():
            ws = None
            try:
                ws = await self.api.async_open_websocket()
                backoff = 1
                async for message in ws:
                    if message.type == WSMsgType.TEXT:
                        payload = json.loads(message.data)
                        state = payload.get("state")
                        if isinstance(state, dict) and state.get("identity", {}).get("client_id") == self.client_id:
                            self.async_set_updated_data(state)
                    elif message.type == WSMsgType.ERROR:
                        break
            except Exception as err:
                LOGGER.debug("Dangbei gateway WebSocket reconnecting: %s", err)
            finally:
                if ws is not None:
                    await ws.close()
            if self._ws_stop.is_set():
                break
            try:
                await asyncio.wait_for(self._ws_stop.wait(), timeout=backoff)
            except TimeoutError:
                pass
            backoff = min(backoff * 2, 30)
