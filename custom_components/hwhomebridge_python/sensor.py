from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.components.sensor import SensorEntity

from .entity import GatewayEntity
from .gateway import GatewayRuntime


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    runtime: GatewayRuntime = hass.data["hwhomebridge_python"]["runtimes"][entry.entry_id]
    async_add_entities([
        GatewaySerialSensor(runtime),
        GatewayChildCountSensor(runtime),
    ])


class GatewaySerialSensor(GatewayEntity, SensorEntity):
    _attr_translation_key = "serial"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, runtime: GatewayRuntime) -> None:
        super().__init__(runtime)
        self._attr_unique_id = f"{runtime.serial}_serial"

    @property
    def native_value(self) -> str:
        return self.runtime.serial


class GatewayChildCountSensor(GatewayEntity, SensorEntity):
    """Expose the number of child-device entries configured for this gateway."""

    _attr_translation_key = "child_count"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, runtime: GatewayRuntime) -> None:
        super().__init__(runtime)
        self._attr_unique_id = f"{runtime.serial}_child_count"

    @property
    def native_value(self) -> int:
        return self.runtime.child_count
