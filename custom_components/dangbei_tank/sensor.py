"""Sensor entities for Dangbei Tank."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_CLIENT_ID
from .entity import DangbeiTankEntity


async def async_setup_entry(hass, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    runtime_data = entry.runtime_data
    coordinator = runtime_data.coordinator
    async_add_entities(
        [
            DangbeiTemperatureSensor(coordinator, entry),
            DangbeiTdsSensor(coordinator, entry),
        ]
    )


class DangbeiTemperatureSensor(DangbeiTankEntity, SensorEntity):
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "water_temperature", "Water Temperature")

    @property
    def native_value(self):
        return self._properties().get("temperature")


class DangbeiTdsSensor(DangbeiTankEntity, SensorEntity):
    _attr_native_unit_of_measurement = "ppm"
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "tds", "TDS")

    @property
    def native_value(self):
        return self._properties().get("tdsSensorValue")
