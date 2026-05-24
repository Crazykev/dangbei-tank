"""Environment-driven gateway configuration."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None else default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value is not None else default


@dataclass(slots=True)
class GatewayConfig:
    """Runtime configuration for the gateway service."""

    client_id: str
    username: str
    password: str
    group: str
    mac: str
    sn: str
    rom_ver_code: str
    local_mqtt_host: str
    local_mqtt_port: int
    local_mqtt_ca_cert: str | None
    local_mqtt_insecure: bool
    cloud_mqtt_host: str
    cloud_mqtt_port: int
    cloud_mqtt_insecure: bool
    api_host: str
    api_port: int
    api_token: str
    info_interval_seconds: int
    snapshot_interval_seconds: int
    command_timeout_seconds: float
    post_command_refresh_delay_seconds: float
    snapshot_throttle_seconds: float
    log_path: str

    @classmethod
    def from_env(cls) -> "GatewayConfig":
        """Load the gateway configuration from environment variables."""
        client_id = os.getenv("DANGBEI_CLIENT_ID", "YUFC012CD19AA8518347")
        username = os.getenv("DANGBEI_USERNAME", client_id)
        return cls(
            client_id=client_id,
            username=username,
            password=os.getenv("DANGBEI_PASSWORD", "YU010387"),
            group=os.getenv("DANGBEI_GROUP", "YU01"),
            mac=os.getenv("DANGBEI_MAC", "FC:01:2C:D1:9A:A8"),
            sn=os.getenv("DANGBEI_SN", "DHYU1S18253518347"),
            rom_ver_code=os.getenv("DANGBEI_ROM_VER_CODE", "2025.01.08.1"),
            local_mqtt_host=os.getenv("LOCAL_MQTT_HOST", "127.0.0.1"),
            local_mqtt_port=_env_int("LOCAL_MQTT_PORT", 8883),
            local_mqtt_ca_cert=os.getenv("LOCAL_MQTT_CA_CERT", "/app/certs/server.crt"),
            local_mqtt_insecure=_env_bool("LOCAL_MQTT_INSECURE", True),
            cloud_mqtt_host=os.getenv("CLOUD_MQTT_HOST", "47.106.145.127"),
            cloud_mqtt_port=_env_int("CLOUD_MQTT_PORT", 8883),
            cloud_mqtt_insecure=_env_bool("CLOUD_MQTT_INSECURE", True),
            api_host=os.getenv("API_HOST", "0.0.0.0"),
            api_port=_env_int("API_PORT", 8787),
            api_token=os.getenv("API_TOKEN", "changeme"),
            info_interval_seconds=_env_int("INFO_INTERVAL_SECONDS", 45),
            snapshot_interval_seconds=_env_int("SNAPSHOT_INTERVAL_SECONDS", 90),
            command_timeout_seconds=_env_float("COMMAND_TIMEOUT_SECONDS", 10.0),
            post_command_refresh_delay_seconds=_env_float("POST_COMMAND_REFRESH_DELAY_SECONDS", 1.0),
            snapshot_throttle_seconds=_env_float("SNAPSHOT_THROTTLE_SECONDS", 1.0),
            log_path=os.getenv("LOG_PATH", "/data/gateway.jsonl"),
        )

    @property
    def info_payload(self) -> str:
        """Return the upstream info payload expected by the vendor cloud."""
        return json.dumps(
            {
                "clientId": self.client_id,
                "mac": self.mac,
                "mode1": self.group,
                "romVerCode": self.rom_ver_code,
                "sn": self.sn,
                "reconnectDuration": 60,
            },
            separators=(",", ":"),
        )
