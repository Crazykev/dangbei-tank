"""In-memory canonical state store for the fish tank gateway."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
import time
from typing import Any


class GatewayState:
    """Thread-safe state store plus push subscriptions."""

    def __init__(self, *, client_id: str, identity: dict[str, Any] | None = None) -> None:
        resolved_identity = {
            "client_id": client_id,
            "mac": None,
            "group": None,
            "sn": None,
            "rom_ver_code": None,
        }
        if identity:
            resolved_identity.update({key: value for key, value in identity.items() if value is not None})
        self._client_id = client_id
        self._lock = asyncio.Lock()
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._state: dict[str, Any] = {
            "identity": resolved_identity,
            "connectivity": {
                "broker_connected": False,
                "cloud_connected": False,
                "device_connected": False,
                "last_upstream_ts": None,
                "last_snapshot_ts": None,
            },
            "properties": {},
            "pending": {},
            "dirty": {
                "needs_refresh": True,
                "reason": "startup",
            },
            "raw": {
                "last_cloud_downlink": None,
                "last_local_reply": None,
                "last_local_event": None,
                "last_snapshot": None,
            },
        }

    async def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        """Register one websocket-style subscriber."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        async with self._lock:
            self._subscribers.add(queue)
            snapshot = deepcopy(self._state)
        await queue.put({"event": "snapshot", "state": snapshot})
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """Remove one subscriber queue."""
        async with self._lock:
            self._subscribers.discard(queue)

    async def snapshot(self) -> dict[str, Any]:
        """Return a copy of the current canonical state."""
        async with self._lock:
            return deepcopy(self._state)

    async def log_record(self, path: str, event: str, **data: Any) -> None:
        """Append one JSONL gateway record."""
        record = {"ts": time.time(), "event": event, **data}
        line = __import__("json").dumps(record, ensure_ascii=True)
        await asyncio.to_thread(self._append_line, path, line)

    @staticmethod
    def _append_line(path: str, line: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    async def set_identity(self, **identity: Any) -> None:
        async with self._lock:
            self._state["identity"].update({key: value for key, value in identity.items() if value is not None})
            payload = {"event": "state_changed", "state": deepcopy(self._state)}
        await self._broadcast(payload)

    async def set_connectivity(self, **connectivity: Any) -> None:
        async with self._lock:
            self._state["connectivity"].update(connectivity)
            payload = {"event": "connectivity_changed", "state": deepcopy(self._state)}
        await self._broadcast(payload)

    async def mark_device_seen(self) -> bool:
        async with self._lock:
            was_connected = bool(self._state["connectivity"].get("device_connected"))
            self._state["connectivity"]["device_connected"] = True
            self._state["connectivity"]["last_upstream_ts"] = time.time()
            payload = {"event": "connectivity_changed", "state": deepcopy(self._state)}
        await self._broadcast(payload)
        return not was_connected

    async def set_device_connected(self, is_connected: bool) -> None:
        await self.set_connectivity(device_connected=is_connected)

    async def set_properties(self, properties: dict[str, Any], *, reason: str = "snapshot") -> None:
        async with self._lock:
            self._state["properties"] = deepcopy(properties)
            self._state["dirty"] = {"needs_refresh": False, "reason": reason}
            self._state["connectivity"]["last_snapshot_ts"] = time.time()
            self._state["raw"]["last_snapshot"] = deepcopy(properties)
            payload = {"event": "state_changed", "state": deepcopy(self._state)}
        await self._broadcast(payload)

    async def merge_properties(self, updates: dict[str, Any], *, reason: str = "event") -> None:
        async with self._lock:
            self._state["properties"].update(deepcopy(updates))
            self._state["dirty"] = {"needs_refresh": False, "reason": reason}
            payload = {"event": "state_changed", "state": deepcopy(self._state)}
        await self._broadcast(payload)

    async def mark_dirty(self, reason: str) -> None:
        async with self._lock:
            self._state["dirty"] = {"needs_refresh": True, "reason": reason}
            payload = {"event": "state_changed", "state": deepcopy(self._state)}
        await self._broadcast(payload)

    async def add_pending(self, msg_id: str, data: dict[str, Any]) -> None:
        async with self._lock:
            self._state["pending"][msg_id] = deepcopy(data)
            payload = {"event": "state_changed", "state": deepcopy(self._state)}
        await self._broadcast(payload)

    async def pop_pending(self, msg_id: str) -> dict[str, Any] | None:
        async with self._lock:
            value = self._state["pending"].pop(msg_id, None)
            payload = {"event": "state_changed", "state": deepcopy(self._state)}
        await self._broadcast(payload)
        return value

    async def clear_pending_by_service(self, service_name: str) -> int:
        async with self._lock:
            pending = self._state["pending"]
            removed = [
                msg_id
                for msg_id, data in pending.items()
                if data.get("service_name") == service_name
            ]
            for msg_id in removed:
                pending.pop(msg_id, None)
            payload = {"event": "state_changed", "state": deepcopy(self._state)}
        await self._broadcast(payload)
        return len(removed)

    async def expire_pending_before(self, cutoff_ts: float) -> list[str]:
        async with self._lock:
            pending = self._state["pending"]
            removed = [
                msg_id
                for msg_id, data in pending.items()
                if float(data.get("created_at", 0.0)) <= cutoff_ts
            ]
            for msg_id in removed:
                pending.pop(msg_id, None)
            payload = {"event": "state_changed", "state": deepcopy(self._state)}
        await self._broadcast(payload)
        return removed

    async def set_raw_field(self, key: str, value: Any) -> None:
        async with self._lock:
            self._state["raw"][key] = deepcopy(value)
            payload = {"event": "state_changed", "state": deepcopy(self._state)}
        await self._broadcast(payload)

    async def _broadcast(self, payload: dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(deepcopy(payload))
            except asyncio.QueueFull:
                pass
