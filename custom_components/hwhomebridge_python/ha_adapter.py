from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later, async_track_state_change_event

from .business.models import BindingField, ChildPlan


_LOGGER = logging.getLogger(__name__)


class HAEntityBridge:
    """Read/call HA entities from the gateway's non-event-loop worker."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    def read_child_state(self, child: ChildPlan) -> dict[str, dict[str, object]]:
        result = self._run(self._async_read_child_state(child))
        _LOGGER.debug("HA state snapshot child=%s state=%s", child.key, result)
        return result

    def apply_child_command(
        self, child: ChildPlan, service_id: str, payload: dict[str, object]
    ) -> None:
        _LOGGER.debug(
            "HA command received child=%s sid=%s payload=%s",
            child.key,
            service_id,
            payload,
        )
        self._run(self._async_apply_child_command(child, service_id, payload))

    def setup_state_listener(self, plan, callback):
        """Forward bound HA state changes to the gateway worker."""

        entity_ids = {
            binding.entity_id
            for child in plan.children
            for binding in child.bindings
            if binding.entity_id
        }
        if not entity_ids:
            return lambda: None

        async def state_changed(event) -> None:
            entity_id = event.data.get("entity_id")
            for child in plan.children:
                if not any(binding.entity_id == entity_id for binding in child.bindings):
                    continue
                snapshot = await self._async_read_child_state(child)
                _LOGGER.debug(
                    "HA state event child=%s entity=%s snapshot=%s",
                    child.key,
                    entity_id,
                    snapshot,
                )
                callback(child.key, snapshot)

        return async_track_state_change_event(self._hass, entity_ids, state_changed)

    def schedule_startup_sync(self, plan, callback, *, attempts: int = 12):
        """Retry initial snapshots while HA entities/cloud session restore."""

        remaining = attempts
        cancel_handle = None

        async def retry(_now) -> None:
            nonlocal remaining, cancel_handle
            pending = False
            for child in plan.children:
                snapshot = await self._async_read_child_state(child)
                if snapshot:
                    _LOGGER.debug(
                        "Startup state snapshot child=%s state=%s",
                        child.key,
                        snapshot,
                    )
                    if callback(child.key, snapshot) is False:
                        pending = True
                else:
                    pending = True
            remaining -= 1
            if pending and remaining > 0:
                cancel_handle = async_call_later(self._hass, 5, retry)

        cancel_handle = async_call_later(self._hass, 2, retry)

        def cancel() -> None:
            if cancel_handle is not None:
                cancel_handle()

        return cancel

    def _run(self, coroutine):
        future = asyncio.run_coroutine_threadsafe(coroutine, self._hass.loop)
        return future.result(timeout=15)

    async def _async_read_child_state(
        self, child: ChildPlan
    ) -> dict[str, dict[str, object]]:
        result: dict[str, dict[str, object]] = {}
        for binding in child.bindings:
            if binding.source in {"constant", "command"}:
                value = _read_binding_value("", {}, binding)
                state_value = f"<{binding.source}>"
            else:
                state = self._hass.states.get(binding.entity_id)
                if state is None or state.state in {"unknown", "unavailable"}:
                    continue
                state_value = state.state
                value = _read_binding_value(state.state, state.attributes, binding)
            _LOGGER.debug(
                "HA binding read child=%s sid=%s field=%s entity=%s "
                "state=%s attribute=%s converted=%s",
                child.key,
                binding.service_id,
                binding.field_name,
                binding.entity_id,
                state_value,
                binding.attribute,
                value,
            )
            if value is None:
                continue
            result.setdefault(binding.service_id, {})[binding.field_name] = value
        return result

    async def _async_apply_child_command(
        self, child: ChildPlan, service_id: str, payload: dict[str, object]
    ) -> None:
        bindings = [binding for binding in child.bindings if binding.service_id == service_id]
        for binding in bindings:
            if binding.field_name not in payload:
                continue
            value = _map_huawei_value(binding, payload[binding.field_name])
            await _call_binding(self._hass, binding, value)


def _read_binding_value(
    state_value: str, attributes: dict[str, Any], binding: BindingField
) -> object | None:
    if binding.source == "constant":
        value: object = binding.value
    elif binding.source == "command":
        return None
    elif binding.source == "state":
        value: object = state_value
    elif binding.source == "attribute" and binding.attribute:
        value = attributes.get(binding.attribute)
    else:
        return None
    if binding.component is not None:
        if not isinstance(value, (tuple, list)) or len(value) < 3:
            return None
        component_index = {"red": 0, "green": 1, "blue": 2}[binding.component]
        value = value[component_index]
    mapping = binding.ha_to_huawei.get("map")
    if isinstance(mapping, dict):
        value = mapping.get(str(value), value)
    if binding.field_name == "brightness" and isinstance(value, (int, float)):
        return max(0, min(100, round(float(value) * 100 / 255)))
    return value


def _map_huawei_value(binding: BindingField, value: object) -> object:
    mapping = binding.huawei_to_ha.get("map")
    if isinstance(mapping, dict):
        return mapping.get(str(value), value)
    return value


async def _call_binding(
    hass: HomeAssistant, binding: BindingField, value: object
) -> None:
    if not binding.entity_id:
        return
    domain, _separator, _object_id = binding.entity_id.partition(".")
    if not domain or not _object_id:
        return
    if binding.field_name == "on":
        is_on = value not in (None, False, 0, "0", "off", "false")
        service = "turn_on" if is_on else "turn_off"
        _LOGGER.debug(
            "Calling HA service %s.%s entity=%s value=%s",
            domain,
            service,
            binding.entity_id,
            value,
        )
        await hass.services.async_call(
            domain, service, {"entity_id": binding.entity_id}, blocking=True
        )
        return
    if binding.field_name == "brightness":
        brightness = max(0, min(100, int(value)))
        _LOGGER.debug(
            "Calling HA service %s.turn_on entity=%s brightness_pct=%s",
            domain,
            binding.entity_id,
            brightness,
        )
        await hass.services.async_call(
            domain,
            "turn_on",
            {"entity_id": binding.entity_id, "brightness_pct": brightness},
            blocking=True,
        )
        return
    if binding.field_name == "colorTemperature":
        _LOGGER.debug(
            "Calling HA service %s.turn_on entity=%s color_temp_kelvin=%s",
            domain,
            binding.entity_id,
            value,
        )
        await hass.services.async_call(
            domain,
            "turn_on",
            {"entity_id": binding.entity_id, "color_temp_kelvin": int(value)},
            blocking=True,
        )
        return
    if domain == "climate" and binding.field_name == "mode":
        _LOGGER.debug(
            "Calling climate.set_hvac_mode entity=%s hvac_mode=%s",
            binding.entity_id,
            value,
        )
        await hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {"entity_id": binding.entity_id, "hvac_mode": str(value)},
            blocking=True,
        )
        return
    if domain == "climate" and binding.field_name == "target":
        _LOGGER.debug(
            "Calling climate.set_temperature entity=%s temperature=%s",
            binding.entity_id,
            value,
        )
        await hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": binding.entity_id, "temperature": float(value)},
            blocking=True,
        )
        return
    if domain == "cover" and binding.field_name == "action":
        services = {0: "close_cover", 1: "open_cover", 2: "stop_cover"}
        service = services.get(int(value))
        if service is None:
            return
        _LOGGER.debug(
            "Calling cover.%s entity=%s action=%s",
            service,
            binding.entity_id,
            value,
        )
        await hass.services.async_call(
            "cover",
            service,
            {"entity_id": binding.entity_id},
            blocking=True,
        )
        return
    if domain == "cover" and binding.field_name == "target":
        _LOGGER.debug(
            "Calling cover.set_cover_position entity=%s position=%s",
            binding.entity_id,
            value,
        )
        await hass.services.async_call(
            "cover",
            "set_cover_position",
            {"entity_id": binding.entity_id, "position": int(value)},
            blocking=True,
        )
        return
    if binding.field_name in {"red", "green", "blue"}:
        state = hass.states.get(binding.entity_id)
        current = state.attributes.get("rgb_color") if state is not None else None
        rgb = list(current) if isinstance(current, (tuple, list)) and len(current) >= 3 else [0, 0, 0]
        component_index = {"red": 0, "green": 1, "blue": 2}[binding.field_name]
        rgb[component_index] = max(0, min(255, int(value)))
        _LOGGER.debug(
            "Calling HA service %s.turn_on entity=%s rgb_color=%s",
            domain,
            binding.entity_id,
            rgb,
        )
        await hass.services.async_call(
            domain,
            "turn_on",
            {"entity_id": binding.entity_id, "rgb_color": tuple(rgb)},
            blocking=True,
        )
