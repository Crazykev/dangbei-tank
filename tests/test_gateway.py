from __future__ import annotations

import asyncio
import json

from dangbei_tank_gateway.config import GatewayConfig
from dangbei_tank_gateway.protocol import (
    build_command_payload,
    build_property_event_payload,
    command_topic,
    event_topic,
    parse_event,
    parse_reply,
)
from dangbei_tank_gateway.service import GatewayService, IncomingMessage
from dangbei_tank_gateway.state import GatewayState


def test_build_command_payload_uses_vendor_shape() -> None:
    payload = build_command_payload("setProperty", {"lightSwitch": 1}, msg_id="123")
    assert payload["msgId"] == "123"
    action = json.loads(payload["content"]["action"])
    assert action == {"serviceName": "setProperty", "items": {"lightSwitch": 1}}


def test_send_command_supports_feed_service_name() -> None:
    async def _run() -> None:
        service = GatewayService(
            GatewayConfig(
                client_id="abc",
                username="abc",
                password="secret",
                group="grp",
                mac="00:11:22:33:44:55",
                sn="sn",
                rom_ver_code="1",
                local_mqtt_host="127.0.0.1",
                local_mqtt_port=8883,
                local_mqtt_ca_cert=None,
                local_mqtt_insecure=True,
                cloud_mqtt_host="127.0.0.1",
                cloud_mqtt_port=8883,
                cloud_mqtt_insecure=True,
                api_host="127.0.0.1",
                api_port=8787,
                api_token="token",
                info_interval_seconds=45,
                snapshot_interval_seconds=90,
                command_timeout_seconds=10.0,
                post_command_refresh_delay_seconds=1.0,
                snapshot_throttle_seconds=1.0,
                log_path="/tmp/dangbei-test.jsonl",
            )
        )
        published: list[tuple[str, str, int, bool]] = []

        def fake_publish(topic: str, payload: str, qos: int, retain: bool) -> None:
            published.append((topic, payload, qos, retain))

        service.local.publish = fake_publish  # type: ignore[method-assign]

        result = await service.send_command(
            "abc",
            service_name="feed",
            items={"num": 1},
            request_id="button_feed_now",
        )

        snapshot = await service.state.snapshot()
        pending = snapshot["pending"][result["msg_id"]]
        assert pending["service_name"] == "feed"
        assert pending["items"] == {"num": 1}
        assert pending["request_id"] == "button_feed_now"
        assert snapshot["properties"] == {}

        assert published == [
            (
                command_topic("abc"),
                json.dumps(
                    {
                        "content": {
                            "action": "{\"serviceName\":\"feed\",\"items\":{\"num\":1}}"
                        },
                        "msgId": result["msg_id"],
                        "type": "cmd",
                    },
                    separators=(",", ":"),
                ),
                1,
                False,
            )
        ]

    asyncio.run(_run())


def test_parse_reply_extracts_snapshot() -> None:
    parsed = parse_reply(
        json.dumps(
            {
                "clientId": "x",
                "type": "cmd",
                "content": {"action": json.dumps({"serviceName": "getAllProperties", "items": {}})},
                "msgId": "1",
                "success": "true",
                "resultMsg": json.dumps({"temperature": 27.9, "waterPump": 2}),
            }
        )
    )
    assert parsed is not None
    assert parsed.service_name == "getAllProperties"
    assert parsed.result == {"temperature": 27.9, "waterPump": 2}


def test_parse_event_marks_unknown_wrapped_events_for_refresh() -> None:
    parsed = parse_event(json.dumps({"eventType": 1, "content": {"event": 4, "eventValue": "1"}}))
    assert parsed is not None
    assert parsed.updates == {}
    assert parsed.needs_refresh is True


def test_parse_event_merges_known_property_updates() -> None:
    parsed = parse_event(json.dumps({"lightSwitch": 1, "waterPump": 2}))
    assert parsed is not None
    assert parsed.updates == {"lightSwitch": 1, "waterPump": 2}
    assert parsed.needs_refresh is False


def test_parse_event_merges_wrapped_property_updates() -> None:
    parsed = parse_event(
        json.dumps(
            {
                "clientId": "abc",
                "eventType": 0,
                "msgId": "1",
                "content": json.dumps({"waterPumpSwitch": 0, "lightSwitch": 1}),
            }
        )
    )
    assert parsed is not None
    assert parsed.updates == {"waterPumpSwitch": 0, "lightSwitch": 1}
    assert parsed.needs_refresh is False


def test_state_snapshot_broadcasts_updates() -> None:
    async def _run() -> None:
        state = GatewayState(client_id="abc")
        queue = await state.subscribe()
        initial = await queue.get()
        assert initial["event"] == "snapshot"
        await state.set_properties({"temperature": 27.9}, reason="snapshot")
        update = await asyncio.wait_for(queue.get(), timeout=1)
        assert update["state"]["properties"]["temperature"] == 27.9

    asyncio.run(_run())


def test_snapshot_reply_clears_mismatched_pending_snapshot_requests() -> None:
    async def _run() -> None:
        service = GatewayService(
            GatewayConfig(
                client_id="abc",
                username="abc",
                password="secret",
                group="grp",
                mac="00:11:22:33:44:55",
                sn="sn",
                rom_ver_code="1",
                local_mqtt_host="127.0.0.1",
                local_mqtt_port=8883,
                local_mqtt_ca_cert=None,
                local_mqtt_insecure=True,
                cloud_mqtt_host="127.0.0.1",
                cloud_mqtt_port=8883,
                cloud_mqtt_insecure=True,
                api_host="127.0.0.1",
                api_port=8787,
                api_token="token",
                info_interval_seconds=45,
                snapshot_interval_seconds=90,
                command_timeout_seconds=10.0,
                post_command_refresh_delay_seconds=1.0,
                snapshot_throttle_seconds=1.0,
                log_path="/tmp/dangbei-test.jsonl",
            )
        )
        await service.state.add_pending(
            "request-msg-id",
            {
                "request_id": "periodic",
                "service_name": "getAllProperties",
                "items": {},
                "created_at": 1.0,
            },
        )
        parsed = parse_reply(
            json.dumps(
                {
                    "clientId": "abc",
                    "type": "cmd",
                    "content": {"action": json.dumps({"serviceName": "getAllProperties", "items": {}})},
                    "msgId": "reply-msg-id",
                    "success": "true",
                    "resultMsg": json.dumps({"temperature": 27.9}),
                }
            )
        )
        assert parsed is not None

        await service._handle_reply(parsed)

        snapshot = await service.state.snapshot()
        assert snapshot["pending"] == {}
        assert snapshot["properties"]["temperature"] == 27.9

    asyncio.run(_run())


def test_cloud_message_marks_cloud_connected_and_config_identity_is_present() -> None:
    async def _run() -> None:
        service = GatewayService(
            GatewayConfig(
                client_id="abc",
                username="abc",
                password="secret",
                group="grp",
                mac="00:11:22:33:44:55",
                sn="sn",
                rom_ver_code="1",
                local_mqtt_host="127.0.0.1",
                local_mqtt_port=8883,
                local_mqtt_ca_cert=None,
                local_mqtt_insecure=True,
                cloud_mqtt_host="127.0.0.1",
                cloud_mqtt_port=8883,
                cloud_mqtt_insecure=True,
                api_host="127.0.0.1",
                api_port=8787,
                api_token="token",
                info_interval_seconds=45,
                snapshot_interval_seconds=90,
                command_timeout_seconds=10.0,
                post_command_refresh_delay_seconds=1.0,
                snapshot_throttle_seconds=1.0,
                log_path="/tmp/dangbei-test.jsonl",
            )
        )

        snapshot_requests: list[str] = []

        async def fake_request_snapshot(reason: str) -> None:
            snapshot_requests.append(reason)

        service.request_snapshot = fake_request_snapshot  # type: ignore[method-assign]
        await service._handle_cloud_message(
            IncomingMessage(
                source="cloud",
                topic="cmd/device/down/abc",
                payload=json.dumps(
                    {
                        "content": {
                            "action": json.dumps({"serviceName": "getAllProperties", "items": {}})
                        },
                        "msgId": "1",
                        "type": "cmd",
                    }
                ),
            )
        )

        snapshot = await service.state.snapshot()
        assert snapshot["connectivity"]["cloud_connected"] is True
        assert snapshot["identity"] == {
            "client_id": "abc",
            "mac": "00:11:22:33:44:55",
            "group": "grp",
            "sn": "sn",
            "rom_ver_code": "1",
        }
        assert snapshot_requests == []

    asyncio.run(_run())


def test_cloud_feed_message_triggers_refresh() -> None:
    async def _run() -> None:
        service = GatewayService(
            GatewayConfig(
                client_id="abc",
                username="abc",
                password="secret",
                group="grp",
                mac="00:11:22:33:44:55",
                sn="sn",
                rom_ver_code="1",
                local_mqtt_host="127.0.0.1",
                local_mqtt_port=8883,
                local_mqtt_ca_cert=None,
                local_mqtt_insecure=True,
                cloud_mqtt_host="127.0.0.1",
                cloud_mqtt_port=8883,
                cloud_mqtt_insecure=True,
                api_host="127.0.0.1",
                api_port=8787,
                api_token="token",
                info_interval_seconds=45,
                snapshot_interval_seconds=90,
                command_timeout_seconds=10.0,
                post_command_refresh_delay_seconds=1.0,
                snapshot_throttle_seconds=1.0,
                log_path="/tmp/dangbei-test.jsonl",
            )
        )
        snapshot_requests: list[str] = []

        async def fake_request_snapshot(reason: str) -> None:
            snapshot_requests.append(reason)

        service.request_snapshot = fake_request_snapshot  # type: ignore[method-assign]
        await service._handle_cloud_message(
            IncomingMessage(
                source="cloud",
                topic="cmd/device/down/abc",
                payload=json.dumps(
                    {
                        "content": {
                            "action": json.dumps(
                                {
                                    "serviceName": "feed",
                                    "items": {"num": 1},
                                }
                            )
                        },
                        "msgId": "1",
                        "type": "cmd",
                    }
                ),
            )
        )

        snapshot = await service.state.snapshot()
        assert snapshot["dirty"] == {"needs_refresh": True, "reason": "cloud_downlink"}
        assert snapshot_requests == ["cloud_downlink"]

    asyncio.run(_run())


def test_connect_callbacks_trigger_expected_snapshot_reasons() -> None:
    async def _run() -> None:
        service = GatewayService(
            GatewayConfig(
                client_id="abc",
                username="abc",
                password="secret",
                group="grp",
                mac="00:11:22:33:44:55",
                sn="sn",
                rom_ver_code="1",
                local_mqtt_host="127.0.0.1",
                local_mqtt_port=8883,
                local_mqtt_ca_cert=None,
                local_mqtt_insecure=True,
                cloud_mqtt_host="127.0.0.1",
                cloud_mqtt_port=8883,
                cloud_mqtt_insecure=True,
                api_host="127.0.0.1",
                api_port=8787,
                api_token="token",
                info_interval_seconds=45,
                snapshot_interval_seconds=90,
                command_timeout_seconds=10.0,
                post_command_refresh_delay_seconds=1.0,
                snapshot_throttle_seconds=0.0,
                log_path="/tmp/dangbei-test.jsonl",
            )
        )
        snapshot_requests: list[str] = []

        async def fake_request_snapshot(reason: str) -> None:
            snapshot_requests.append(reason)

        service.request_snapshot = fake_request_snapshot  # type: ignore[method-assign]

        await service._async_handle_local_connect()
        await service._async_handle_cloud_connect()
        await service.state.set_properties({"temperature": 28}, reason="snapshot")
        await service._async_handle_local_connect()

        snapshot = await service.state.snapshot()
        assert snapshot["connectivity"]["broker_connected"] is True
        assert snapshot["connectivity"]["cloud_connected"] is True
        assert snapshot_requests == ["startup", "cloud_reconnect", "broker_reconnect"]

    asyncio.run(_run())


def test_pending_timeout_marks_dirty_and_requests_snapshot() -> None:
    async def _run() -> None:
        service = GatewayService(
            GatewayConfig(
                client_id="abc",
                username="abc",
                password="secret",
                group="grp",
                mac="00:11:22:33:44:55",
                sn="sn",
                rom_ver_code="1",
                local_mqtt_host="127.0.0.1",
                local_mqtt_port=8883,
                local_mqtt_ca_cert=None,
                local_mqtt_insecure=True,
                cloud_mqtt_host="127.0.0.1",
                cloud_mqtt_port=8883,
                cloud_mqtt_insecure=True,
                api_host="127.0.0.1",
                api_port=8787,
                api_token="token",
                info_interval_seconds=45,
                snapshot_interval_seconds=90,
                command_timeout_seconds=10.0,
                post_command_refresh_delay_seconds=1.0,
                snapshot_throttle_seconds=0.0,
                log_path="/tmp/dangbei-test.jsonl",
            )
        )
        snapshot_requests: list[str] = []

        async def fake_request_snapshot(reason: str) -> None:
            snapshot_requests.append(reason)

        service.request_snapshot = fake_request_snapshot  # type: ignore[method-assign]
        await service.state.add_pending(
            "expired-msg-id",
            {
                "request_id": "set_property",
                "service_name": "setProperty",
                "items": {"lightSwitch": 1},
                "created_at": 0.0,
            },
        )

        await service._expire_pending_commands_once()

        snapshot = await service.state.snapshot()
        assert snapshot["pending"] == {}
        assert snapshot["dirty"] == {"needs_refresh": True, "reason": "command_timeout"}
        assert snapshot_requests == ["command_timeout"]

    asyncio.run(_run())


def test_local_set_property_reply_publishes_synthetic_cloud_event() -> None:
    async def _run() -> None:
        service = GatewayService(
            GatewayConfig(
                client_id="abc",
                username="abc",
                password="secret",
                group="grp",
                mac="00:11:22:33:44:55",
                sn="sn",
                rom_ver_code="1",
                local_mqtt_host="127.0.0.1",
                local_mqtt_port=8883,
                local_mqtt_ca_cert=None,
                local_mqtt_insecure=True,
                cloud_mqtt_host="127.0.0.1",
                cloud_mqtt_port=8883,
                cloud_mqtt_insecure=True,
                api_host="127.0.0.1",
                api_port=8787,
                api_token="token",
                info_interval_seconds=45,
                snapshot_interval_seconds=90,
                command_timeout_seconds=10.0,
                post_command_refresh_delay_seconds=0.0,
                snapshot_throttle_seconds=0.0,
                log_path="/tmp/dangbei-test.jsonl",
            )
        )
        cloud_publishes: list[tuple[str, str, int, bool]] = []
        snapshot_requests: list[str] = []

        def fake_cloud_publish(topic: str, payload: str, qos: int, retain: bool) -> None:
            cloud_publishes.append((topic, payload, qos, retain))

        async def fake_request_snapshot(reason: str) -> None:
            snapshot_requests.append(reason)

        service.cloud.publish = fake_cloud_publish  # type: ignore[method-assign]
        service.request_snapshot = fake_request_snapshot  # type: ignore[method-assign]
        service.cloud.is_connected = lambda: True  # type: ignore[method-assign]
        await service.state.add_pending(
            "local-msg-id",
            {
                "request_id": None,
                "service_name": "setProperty",
                "items": {"waterPumpSwitch": 1},
                "created_at": 1.0,
            },
        )
        parsed = parse_reply(
            json.dumps(
                {
                    "clientId": "abc",
                    "type": "cmd",
                    "content": {"action": json.dumps({"serviceName": "setProperty", "items": {"waterPumpSwitch": 1}})},
                    "msgId": "local-msg-id",
                    "success": "true",
                    "resultMsg": "",
                }
            )
        )
        assert parsed is not None

        await service._handle_reply(parsed)

        expected_payload = json.dumps(
            build_property_event_payload("abc", {"waterPumpSwitch": 1}),
            separators=(",", ":"),
        )
        assert len(cloud_publishes) == 1
        published_topic, published_payload, published_qos, published_retain = cloud_publishes[0]
        assert published_topic == event_topic("abc")
        published_event = json.loads(published_payload)
        expected_event = json.loads(expected_payload)
        assert published_event["clientId"] == expected_event["clientId"]
        assert published_event["eventType"] == expected_event["eventType"]
        assert json.loads(published_event["content"]) == json.loads(expected_event["content"])
        assert isinstance(published_event["msgId"], str)
        assert published_event["msgId"]
        assert published_qos == 1
        assert published_retain is False
        assert snapshot_requests == ["set_property_ack"]

    asyncio.run(_run())
