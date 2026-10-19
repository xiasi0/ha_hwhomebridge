from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .entity import GatewayEntity
from .gateway import GatewayRuntime


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    runtime: GatewayRuntime = hass.data["hwhomebridge_python"]["runtimes"][entry.entry_id]
    async_add_entities([GatewayOnlineEntity(runtime)])


class GatewayOnlineEntity(GatewayEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "online"

    def __init__(self, runtime: GatewayRuntime) -> None:
        super().__init__(runtime)
        self._attr_unique_id = f"{runtime.serial}_online"

    @property
    def is_on(self) -> bool:
        return self.runtime.status == "online"

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        return {"phase": self.runtime.status}

    @property
    def available(self) -> bool:
        return self.runtime.status != "stopped"
