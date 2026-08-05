"""Diagnostics support for Yunmai Scale."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.redact import async_redact_data

from .const import CONF_PROFILES, DOMAIN
from .manager import YunmaiScaleManager

_TO_REDACT = {
    CONF_ADDRESS,
    CONF_PROFILES,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return privacy-safe diagnostics for one Yunmai config entry."""
    manager: YunmaiScaleManager = hass.data[DOMAIN][entry.entry_id]

    return {
        "config_entry": {
            "version": entry.version,
            "minor_version": entry.minor_version,
            "data": async_redact_data(dict(entry.data), _TO_REDACT),
            "options": async_redact_data(dict(entry.options), _TO_REDACT),
        },
        "runtime": manager.diagnostics,
    }
