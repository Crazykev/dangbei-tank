"""Binary sensors for Dangbei Tank."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import DangbeiTankEntity


async def async_setup_entry(hass, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            DangbeiWaterLevelSensor(coordinator, entry),
            DangbeiTemperatureProbeSensor(coordinator, entry),
            DangbeiCloudConnectivitySensor(coordinator, entry),
            DangbeiDeviceConnectivitySensor(coordinator, entry),
        ]
    )


class DangbeiWaterLevelSensor(DangbeiTankEntity, BinarySensorEntity):
    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "water_level_ok", "Water Level OK")

    @property
    def is_on(self):
        return self._properties().get("waterLevelStatus") == 1


class DangbeiTemperatureProbeSensor(DangbeiTankEntity, BinarySensorEntity):
    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "temperature_probe_ok", "Temperature Probe OK")

    @property
    def is_on(self):
        return self._properties().get("temperatureSensorStatus") == 1


class DangbeiCloudConnectivitySensor(DangbeiTankEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = __import__("homeassistant.helpers.entity", fromlist=["EntityCategory"]).EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "cloud_connected", "Cloud Connected")

    @property
    def is_on(self):
        return bool(self._connectivity().get("cloud_connected"))


class DangbeiDeviceConnectivitySensor(DangbeiTankEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = __import__("homeassistant.helpers.entity", fromlist=["EntityCategory"]).EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "device_connected", "Device Connected")

    @property
    def is_on(self):
        return bool(self._connectivity().get("device_connected"))
