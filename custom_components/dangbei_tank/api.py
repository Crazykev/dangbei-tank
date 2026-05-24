"""HTTP and WebSocket client for the gateway service."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse, urlunparse

from aiohttp import ClientResponseError, ClientSession
from aiohttp.client_ws import ClientWebSocketResponse


class GatewayApiError(Exception):
    """Raised when the gateway API returns an error."""


class GatewayApiClient:
    """Thin async client for the Dangbei gateway."""

    def __init__(self, session: ClientSession, base_url: str, api_token: str) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._api_token = api_token

    @property
    def base_url(self) -> str:
        return self._base_url

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_token}"}

    async def async_get_devices(self) -> list[dict[str, Any]]:
        return await self._request_json("GET", "/api/v1/devices")

    async def async_get_state(self, client_id: str) -> dict[str, Any]:
        return await self._request_json("GET", f"/api/v1/devices/{client_id}/state")

    async def async_send_command(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._request_json(
            "POST",
            f"/api/v1/devices/{client_id}/commands",
            json_data=payload,
        )

    async def async_get_diagnostics(self, client_id: str) -> dict[str, Any]:
        return await self._request_json("GET", f"/api/v1/devices/{client_id}/diagnostics")

    async def async_refresh_state(self, client_id: str) -> dict[str, Any]:
        await self.async_send_command(client_id, {"service_name": "getAllProperties", "items": {}})
        return await self.async_get_state(client_id)

    async def async_open_websocket(self) -> ClientWebSocketResponse:
        ws_url = _http_to_ws(f"{self._base_url}/api/v1/ws")
        return await self._session.ws_connect(ws_url, headers=self._headers())

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_data: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self._base_url}{path}"
        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers(),
                json=json_data,
            ) as response:
                response.raise_for_status()
                return await response.json()
        except ClientResponseError as err:
            raise GatewayApiError(f"Gateway API error {err.status}: {err.message}") from err
        except Exception as err:
            raise GatewayApiError(str(err)) from err


def _http_to_ws(url: str) -> str:
    parsed = urlparse(url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
