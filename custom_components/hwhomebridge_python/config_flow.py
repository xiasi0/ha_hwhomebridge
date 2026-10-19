from __future__ import annotations

import secrets
import socket

import psutil
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import CONF_INTERFACE_IP, CONF_MAC, CONF_SERIAL, DOMAIN


def _interface_options() -> dict[str, str]:
    options: dict[str, str] = {}
    for name, addresses in psutil.net_if_addrs().items():
        for address in addresses:
            if address.family != socket.AF_INET:
                continue
            if address.address.startswith("127."):
                continue
            options[address.address] = f"{name} — {address.address}"
    return options


def _interface_mac(interface_ip: str) -> str:
    for _name, addresses in psutil.net_if_addrs().items():
        ipv4 = {address.address for address in addresses if address.family == socket.AF_INET}
        if interface_ip not in ipv4:
            continue
        for address in addresses:
            if getattr(address.family, "name", "") in {"AF_LINK", "AF_PACKET"}:
                value = address.address.replace(":", "").replace("-", "").upper()
                if len(value) == 12:
                    return value
    raise ValueError(f"no MAC address found for interface {interface_ip}")


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create the HA entry and let the gateway pair asynchronously."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        options = await self.hass.async_add_executor_job(_interface_options)
        if not options:
            return self.async_abort(reason="no_ipv4_interface")

        errors: dict[str, str] = {}
        if user_input is not None:
            interface_ip = user_input[CONF_INTERFACE_IP]
            try:
                mac = await self.hass.async_add_executor_job(
                    _interface_mac, interface_ip
                )
            except ValueError:
                errors[CONF_INTERFACE_IP] = "mac_not_found"
            else:
                serial = secrets.token_hex(8).upper()
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=serial,
                    data={
                        CONF_INTERFACE_IP: interface_ip,
                        CONF_MAC: mac,
                        CONF_SERIAL: serial,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_INTERFACE_IP): vol.In(options)}
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return OptionsFlow(config_entry)


class OptionsFlow(config_entries.OptionsFlow):
    """Allow the user to change the manually selected LAN interface."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        options = await self.hass.async_add_executor_job(_interface_options)
        if user_input is not None:
            interface_ip = user_input[CONF_INTERFACE_IP]
            mac = await self.hass.async_add_executor_job(_interface_mac, interface_ip)
            return self.async_create_entry(
                title="",
                data={CONF_INTERFACE_IP: interface_ip, CONF_MAC: mac},
            )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_INTERFACE_IP,
                        default=self._entry.data.get(CONF_INTERFACE_IP),
                    ): vol.In(options)
                }
            ),
        )
