"""Protocol helpers for Dangbei fish tank MQTT payloads."""

from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any

KNOWN_EVENT_KEYS = {
    "buzzerSwitch",
    "childLockSwitch",
    "customLightBrightness",
    "customLightColor",
    "feedPauseTime",
    "feedingProtectionSwitch",
    "filtrationStatus",
    "indLightDisplayMode",
    "indLightDisplaySwitch",
    "lightBrightness",
    "lightMode",
    "lightSpeed",
    "lightSwitch",
    "maxTdsSensorValue",
    "maxTemperature",
    "minTdsSensorValue",
    "minTemperature",
    "peripheralNum",
    "peripheralPowerSwitch_1",
    "peripheralPowerSwitch_2",
    "powerSupplyMode",
    "powerSwitch",
    "reconnectDuration",
    "tdsAlertSwitch",
    "tdsCoefficient",
    "tdsSensorValue",
    "temperature",
    "temperatureSensorStatus",
    "waterLevelStatus",
    "waterPump",
    "waterPumpStatus",
    "waterPumpSwitch",
}


@dataclass(slots=True)
class ParsedReply:
    """Structured representation of one device reply."""

    msg_id: str
    service_name: str | None
    items: dict[str, Any]
    success: bool
    result: dict[str, Any] | None
    raw: dict[str, Any]


@dataclass(slots=True)
class ParsedEvent:
    """Structured representation of one device event."""

    updates: dict[str, Any]
    raw: dict[str, Any]
    needs_refresh: bool


def command_topic(client_id: str) -> str:
    return f"cmd/device/down/{client_id}"


def reply_topic(client_id: str) -> str:
    return f"message/device/up/reply/{client_id}"


def event_topic(client_id: str) -> str:
    return f"message/device/up/event/{client_id}"


def info_topic(client_id: str) -> str:
    return f"message/device/up/info/{client_id}"


def cloud_down_topics(client_id: str, group: str) -> list[str]:
    return [
        f"cmd/device/down/{client_id}",
        f"config/device/down/{client_id}",
        f"cmd/broadcast/down/group/{group}",
        f"config/broadcast/down/group/{group}",
    ]


def new_msg_id() -> str:
    return str(int(time.time() * 1_000_000_000))[:18]


def decode_json_payload(payload: str) -> dict[str, Any] | None:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def decode_action(raw_action: Any) -> dict[str, Any] | None:
    if isinstance(raw_action, dict):
        return raw_action
    if not isinstance(raw_action, str):
        return None
    try:
        data = json.loads(raw_action)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def build_command_payload(
    service_name: str,
    items: dict[str, Any] | None = None,
    *,
    msg_id: str | None = None,
) -> dict[str, Any]:
    """Build the vendor-style downlink envelope."""
    if items is None:
        items = {}

    return {
        "content": {
            "action": json.dumps(
                {
                    "serviceName": service_name,
                    "items": items,
                },
                separators=(",", ":"),
            )
        },
        "msgId": msg_id or new_msg_id(),
        "type": "cmd",
    }


def parse_reply(payload: str) -> ParsedReply | None:
    """Parse one reply payload from the device."""
    data = decode_json_payload(payload)
    if data is None:
        return None

    action = decode_action(data.get("content", {}).get("action"))
    result_payload = data.get("resultMsg")
    result: dict[str, Any] | None = None
    if isinstance(result_payload, str) and result_payload:
        result = decode_json_payload(result_payload)

    items = action.get("items", {}) if isinstance(action, dict) else {}
    return ParsedReply(
        msg_id=str(data.get("msgId", "")),
        service_name=action.get("serviceName") if isinstance(action, dict) else None,
        items=items if isinstance(items, dict) else {},
        success=str(data.get("success", "")).lower() == "true",
        result=result,
        raw=data,
    )


def parse_info(payload: str) -> dict[str, Any] | None:
    """Parse the upstream info payload."""
    return decode_json_payload(payload)


def parse_event(payload: str) -> ParsedEvent | None:
    """Parse one device event payload into state updates."""
    data = decode_json_payload(payload)
    if data is None:
        return None

    updates: dict[str, Any] = {}
    for key, value in data.items():
        if key in KNOWN_EVENT_KEYS:
            updates[key] = value

    needs_refresh = not updates
    if "content" in data and "eventType" in data:
        needs_refresh = True

    return ParsedEvent(
        updates=updates,
        raw=data,
        needs_refresh=needs_refresh,
    )
