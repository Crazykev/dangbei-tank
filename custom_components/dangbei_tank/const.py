"""Constants for the Dangbei Tank integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "dangbei_tank"

CONF_API_TOKEN = "api_token"
CONF_AREA_ID = "area_id"
CONF_CLIENT_ID = "client_id"
CONF_DISPLAY_NAME = "display_name"
CONF_ENTRY_ID = "entry_id"
CONF_GATEWAY_BASE_URL = "gateway_base_url"

DEFAULT_NAME = "Dangbei Fish Tank"

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.NUMBER,
]

SERVICE_DUMP_LAST_RAW_PAYLOADS = "dump_last_raw_payloads"
SERVICE_REFRESH_STATE = "refresh_state"
SERVICE_SEND_RAW_COMMAND = "send_raw_command"
