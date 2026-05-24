"""Core gateway service implementation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import time
from typing import Any

import paho.mqtt.client as mqtt

from .config import GatewayConfig
from .protocol import (
    ParsedEvent,
    ParsedReply,
    build_command_payload,
    cloud_down_topics,
    command_topic,
    decode_action,
    event_topic,
    info_topic,
    parse_event,
    parse_info,
    parse_reply,
)
from .state import GatewayState


@dataclass(slots=True)
class IncomingMessage:
    """One message routed into the async state reducer."""

    source: str
    topic: str
    payload: str


class GatewayService:
    """Owns MQTT sessions, canonical state, and gateway APIs."""

    def __init__(self, config: GatewayConfig) -> None:
        self.config = config
        self.state = GatewayState(
            client_id=config.client_id,
            identity={
                "mac": config.mac,
                "group": config.group,
                "sn": config.sn,
                "rom_ver_code": config.rom_ver_code,
            },
        )
        self.loop: asyncio.AbstractEventLoop | None = None
        self.queue: asyncio.Queue[IncomingMessage] = asyncio.Queue()
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task[Any]] = []
        self._last_snapshot_request_ts = 0.0
        self._last_info_ts = 0.0

        self.local = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="dangbei-gateway-local",
            protocol=mqtt.MQTTv311,
        )
        if config.local_mqtt_ca_cert:
            self.local.tls_set(ca_certs=config.local_mqtt_ca_cert)
            self.local.tls_insecure_set(config.local_mqtt_insecure)
        self.local.on_connect = self._on_local_connect
        self.local.on_disconnect = self._on_local_disconnect
        self.local.on_message = self._on_local_message
        self.local.reconnect_delay_set(min_delay=1, max_delay=10)

        self.cloud = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=config.client_id,
            protocol=mqtt.MQTTv5,
        )
        self.cloud.username_pw_set(config.username, config.password)
        self.cloud.tls_set()
        self.cloud.tls_insecure_set(config.cloud_mqtt_insecure)
        self.cloud.on_connect = self._on_cloud_connect
        self.cloud.on_disconnect = self._on_cloud_disconnect
        self.cloud.on_message = self._on_cloud_message
        self.cloud.reconnect_delay_set(min_delay=1, max_delay=10)

    async def start(self) -> None:
        """Start background tasks and both MQTT clients."""
        self.loop = asyncio.get_running_loop()
        self.local.connect(self.config.local_mqtt_host, self.config.local_mqtt_port, keepalive=60)
        self.cloud.connect(self.config.cloud_mqtt_host, self.config.cloud_mqtt_port, keepalive=60)
        self.local.loop_start()
        self.cloud.loop_start()
        self._tasks = [
            asyncio.create_task(self._process_queue(), name="dangbei-process-queue"),
            asyncio.create_task(self._periodic_snapshots(), name="dangbei-periodic-snapshots"),
            asyncio.create_task(self._periodic_info_publish(), name="dangbei-periodic-info"),
            asyncio.create_task(self._pending_timeout_watchdog(), name="dangbei-pending-timeouts"),
        ]
        await self.state.log_record(self.config.log_path, "gateway_started")

    async def stop(self) -> None:
        """Stop tasks and disconnect from MQTT."""
        self._stop.set()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self.local.loop_stop()
        self.cloud.loop_stop()
        try:
            self.local.disconnect()
        except Exception:
            pass
        try:
            self.cloud.disconnect()
        except Exception:
            pass
        await self.state.log_record(self.config.log_path, "gateway_stopped")

    async def list_devices(self) -> list[dict[str, Any]]:
        """Return the one currently supported fish tank as a list item."""
        snapshot = await self.state.snapshot()
        identity = snapshot["identity"]
        return [
            {
                "client_id": identity["client_id"],
                "display_name": "Dangbei Fish Tank",
                "identity": identity,
                "connectivity": snapshot["connectivity"],
            }
        ]

    async def get_state(self, client_id: str) -> dict[str, Any]:
        """Return the current state for one client."""
        if client_id != self.config.client_id:
            raise KeyError(client_id)
        return await self.state.snapshot()

    async def send_command(
        self,
        client_id: str,
        *,
        service_name: str,
        items: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Send one standard command to the device."""
        if client_id != self.config.client_id:
            raise KeyError(client_id)

        payload = build_command_payload(service_name, items or {})
        msg_id = str(payload["msgId"])
        if service_name == "getAllProperties":
            await self.state.clear_pending_by_service(service_name)
        await self.state.add_pending(
            msg_id,
            {
                "request_id": request_id,
                "service_name": service_name,
                "items": items or {},
                "created_at": time.time(),
            },
        )
        if service_name == "setProperty" and items:
            await self.state.merge_properties(items, reason="optimistic_write")
        self.local.publish(
            command_topic(self.config.client_id),
            json.dumps(payload, separators=(",", ":")),
            qos=1,
            retain=False,
        )
        await self.state.log_record(
            self.config.log_path,
            "command_sent",
            topic=command_topic(self.config.client_id),
            payload=payload,
            request_id=request_id,
        )
        return {"msg_id": msg_id, "service_name": service_name, "items": items or {}}

    async def send_raw_command(
        self,
        client_id: str,
        *,
        topic: str,
        payload: str,
    ) -> dict[str, Any]:
        """Publish a raw MQTT payload."""
        if client_id != self.config.client_id:
            raise KeyError(client_id)
        self.local.publish(topic, payload, qos=1, retain=False)
        await self.state.log_record(
            self.config.log_path,
            "raw_command_sent",
            topic=topic,
            payload=payload,
        )
        return {"topic": topic, "payload": payload}

    async def diagnostics(self, client_id: str) -> dict[str, Any]:
        """Return diagnostics without redacting gateway-side state."""
        if client_id != self.config.client_id:
            raise KeyError(client_id)
        return await self.state.snapshot()

    async def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        """Register one state subscriber."""
        return await self.state.subscribe()

    async def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """Remove one state subscriber."""
        await self.state.unsubscribe(queue)

    def _enqueue(self, message: IncomingMessage) -> None:
        if self.loop is None:
            return
        self.loop.call_soon_threadsafe(self.queue.put_nowait, message)

    def _schedule(self, coro: asyncio.Future[Any] | asyncio.Task[Any] | Any) -> None:
        if self.loop is None:
            return
        asyncio.run_coroutine_threadsafe(coro, self.loop)

    def _on_local_connect(self, client, userdata, flags, reason_code, properties) -> None:
        client.subscribe("message/device/up/#", qos=1)
        self._schedule(self._async_handle_local_connect())

    def _on_local_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        self._schedule(self._async_handle_local_disconnect())

    def _on_cloud_connect(self, client, userdata, flags, reason_code, properties) -> None:
        for topic in cloud_down_topics(self.config.client_id, self.config.group):
            client.subscribe(topic, qos=1)
        self._last_info_ts = time.time()
        client.publish(info_topic(self.config.client_id), self.config.info_payload, qos=1, retain=False)
        self._schedule(self._async_handle_cloud_connect())

    def _on_cloud_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        self._schedule(self._async_handle_cloud_disconnect())

    def _on_local_message(self, client, userdata, msg) -> None:
        payload = msg.payload.decode("utf-8", errors="replace")
        self.cloud.publish(msg.topic, msg.payload, qos=1, retain=False)
        self._enqueue(IncomingMessage(source="local", topic=msg.topic, payload=payload))

    def _on_cloud_message(self, client, userdata, msg) -> None:
        payload = msg.payload.decode("utf-8", errors="replace")
        self.local.publish(msg.topic, msg.payload, qos=1, retain=False)
        self._enqueue(IncomingMessage(source="cloud", topic=msg.topic, payload=payload))

    async def _process_queue(self) -> None:
        while not self._stop.is_set():
            message = await self.queue.get()
            await self.state.log_record(
                self.config.log_path,
                "message_seen",
                source=message.source,
                topic=message.topic,
                payload=message.payload,
            )
            if message.source == "local":
                first_seen = await self.state.mark_device_seen()
                if first_seen:
                    await self.request_snapshot("device_reconnect")
                await self._handle_local_message(message)
            else:
                await self._handle_cloud_message(message)

    async def _async_handle_local_connect(self) -> None:
        snapshot = await self.state.snapshot()
        reason = "startup" if snapshot["connectivity"].get("last_snapshot_ts") is None else "broker_reconnect"
        await self.state.set_connectivity(broker_connected=True)
        await self.request_snapshot(reason)

    async def _async_handle_local_disconnect(self) -> None:
        await self.state.set_connectivity(broker_connected=False)
        await self.state.set_device_connected(False)

    async def _async_handle_cloud_connect(self) -> None:
        await self.state.set_connectivity(cloud_connected=True)
        await self.request_snapshot("cloud_reconnect")

    async def _async_handle_cloud_disconnect(self) -> None:
        await self.state.set_connectivity(cloud_connected=False)

    async def _handle_local_message(self, message: IncomingMessage) -> None:
        if message.topic == info_topic(self.config.client_id):
            info = parse_info(message.payload)
            if info:
                await self.state.set_identity(
                    mac=info.get("mac"),
                    group=info.get("mode1"),
                    sn=info.get("sn"),
                    rom_ver_code=info.get("romVerCode"),
                )
            return

        if message.topic == event_topic(self.config.client_id):
            parsed = parse_event(message.payload)
            if parsed is None:
                return
            await self.state.set_raw_field("last_local_event", parsed.raw)
            if parsed.updates:
                await self.state.merge_properties(parsed.updates, reason="event")
            if parsed.needs_refresh:
                await self.request_snapshot("event_requires_refresh")
            return

        if message.topic == command_topic(self.config.client_id):
            return

        if message.topic.endswith(f"/reply/{self.config.client_id}"):
            parsed = parse_reply(message.payload)
            if parsed is None:
                return
            await self._handle_reply(parsed)

    async def _handle_reply(self, parsed: ParsedReply) -> None:
        await self.state.set_raw_field("last_local_reply", parsed.raw)
        await self.state.pop_pending(parsed.msg_id)
        if parsed.service_name == "getAllProperties" and parsed.result is not None:
            await self.state.clear_pending_by_service("getAllProperties")
            await self.state.set_properties(parsed.result, reason="snapshot")
            return

        if parsed.service_name == "setProperty" and parsed.success:
            await asyncio.sleep(self.config.post_command_refresh_delay_seconds)
            await self.request_snapshot("set_property_ack")
            return

        await self.request_snapshot("reply_fallback")

    async def _handle_cloud_message(self, message: IncomingMessage) -> None:
        payload = None
        decoded = None
        service_name = None
        if message.payload.startswith("{"):
            try:
                payload = json.loads(message.payload)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                decoded = decode_action(payload.get("content", {}).get("action"))
                if isinstance(decoded, dict):
                    service_name = decoded.get("serviceName")
        await self.state.set_connectivity(cloud_connected=True)
        await self.state.set_raw_field(
            "last_cloud_downlink",
            {
                "topic": message.topic,
                "payload": message.payload,
                "action": decoded,
            },
        )
        if service_name == "getAllProperties":
            return
        await self.state.mark_dirty("cloud_downlink")
        await self.request_snapshot("cloud_downlink")

    async def request_snapshot(self, reason: str) -> None:
        """Throttle and send one snapshot request."""
        now = time.time()
        if now - self._last_snapshot_request_ts < self.config.snapshot_throttle_seconds:
            return
        self._last_snapshot_request_ts = now
        await self.send_command(self.config.client_id, service_name="getAllProperties", request_id=reason)

    async def _periodic_snapshots(self) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(self.config.snapshot_interval_seconds)
            await self.request_snapshot("periodic")

    async def _periodic_info_publish(self) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(1)
            if self.cloud.is_connected() and time.time() - self._last_info_ts >= self.config.info_interval_seconds:
                self.cloud.publish(info_topic(self.config.client_id), self.config.info_payload, qos=1, retain=False)
                self._last_info_ts = time.time()
                await self.state.log_record(
                    self.config.log_path,
                    "cloud_publish_info",
                    topic=info_topic(self.config.client_id),
                    payload=self.config.info_payload,
                )

    async def _pending_timeout_watchdog(self) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(1)
            await self._expire_pending_commands_once()

    async def _expire_pending_commands_once(self) -> None:
        cutoff_ts = time.time() - self.config.command_timeout_seconds
        expired = await self.state.expire_pending_before(cutoff_ts)
        if not expired:
            return
        await self.state.log_record(
            self.config.log_path,
            "command_timeout",
            expired_msg_ids=expired,
        )
        await self.state.mark_dirty("command_timeout")
        await self.request_snapshot("command_timeout")
