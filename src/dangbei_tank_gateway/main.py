"""FastAPI entrypoint for the fish tank gateway."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
import uvicorn

from .config import GatewayConfig
from .service import GatewayService


class CommandRequest(BaseModel):
    """Normalized HTTP command request."""

    service_name: str | None = None
    items: dict[str, Any] = Field(default_factory=dict)
    topic: str | None = None
    payload: str | None = None
    request_id: str | None = None


def create_app(config: GatewayConfig | None = None) -> FastAPI:
    """Build the gateway ASGI application."""
    gateway_config = config or GatewayConfig.from_env()
    service = GatewayService(gateway_config)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.config = gateway_config
        app.state.service = service
        await service.start()
        try:
            yield
        finally:
            await service.stop()

    app = FastAPI(title="Dangbei Tank Gateway", version="0.1.0", lifespan=lifespan)

    def _auth_token(
        authorization: str | None = Header(default=None),
    ) -> None:
        expected = gateway_config.api_token
        if not expected:
            return
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
        token = authorization.removeprefix("Bearer ").strip()
        if token != expected:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/devices", dependencies=[Depends(_auth_token)])
    async def list_devices() -> list[dict[str, Any]]:
        return await service.list_devices()

    @app.get("/api/v1/devices/{client_id}/state", dependencies=[Depends(_auth_token)])
    async def get_state(client_id: str) -> dict[str, Any]:
        try:
            return await service.get_state(client_id)
        except KeyError as err:
            raise HTTPException(status_code=404, detail="Unknown client_id") from err

    @app.post("/api/v1/devices/{client_id}/commands", dependencies=[Depends(_auth_token)])
    async def send_command(client_id: str, request: CommandRequest) -> dict[str, Any]:
        try:
            if request.topic and request.payload is not None:
                return await service.send_raw_command(
                    client_id,
                    topic=request.topic,
                    payload=request.payload,
                )
            if not request.service_name:
                raise HTTPException(status_code=400, detail="service_name is required for standard commands")
            return await service.send_command(
                client_id,
                service_name=request.service_name,
                items=request.items,
                request_id=request.request_id,
            )
        except KeyError as err:
            raise HTTPException(status_code=404, detail="Unknown client_id") from err

    @app.get("/api/v1/devices/{client_id}/diagnostics", dependencies=[Depends(_auth_token)])
    async def diagnostics(client_id: str) -> dict[str, Any]:
        try:
            return await service.diagnostics(client_id)
        except KeyError as err:
            raise HTTPException(status_code=404, detail="Unknown client_id") from err

    @app.websocket("/api/v1/ws")
    async def websocket_endpoint(
        websocket: WebSocket,
        token: str | None = Query(default=None),
    ) -> None:
        expected = gateway_config.api_token
        header_value = websocket.headers.get("authorization", "")
        header_token = header_value.removeprefix("Bearer ").strip() if header_value.startswith("Bearer ") else None
        if expected and token != expected and header_token != expected:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        await websocket.accept()
        queue = await service.subscribe()
        try:
            while True:
                payload = await queue.get()
                await websocket.send_json(payload)
        except WebSocketDisconnect:
            pass
        finally:
            await service.unsubscribe(queue)

    return app


app = create_app()


def run() -> None:
    """Launch the gateway with uvicorn."""
    config = GatewayConfig.from_env()
    uvicorn.run(
        "dangbei_tank_gateway.main:create_app",
        factory=True,
        host=config.api_host,
        port=config.api_port,
    )
