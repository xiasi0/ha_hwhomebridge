from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.components.button import ButtonEntity

from .entity import GatewayEntity
from .gateway import GatewayRuntime


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    runtime: GatewayRuntime = hass.data["hwhomebridge_python"]["runtimes"][entry.entry_id]
    async_add_entities([GatewayReloadChildrenButton(hass, entry, runtime)])


class GatewayReloadChildrenButton(GatewayEntity, ButtonEntity):
    _attr_translation_key = "reload_children"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, runtime: GatewayRuntime) -> None:
        super().__init__(runtime)
        self._hass = hass
        self._entry = entry
        self._attr_unique_id = f"{runtime.serial}_reload_children"

    async def async_press(self) -> None:
        callback = self._hass.data["hwhomebridge_python"].get(
            "reload_callbacks", {}
        ).get(self._entry.entry_id)
        if callback is not None:
            await callback()
