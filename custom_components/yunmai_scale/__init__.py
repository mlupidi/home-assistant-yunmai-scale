"""Yunmai Scale integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from .const import CONF_DEVICE_NAME, CONF_PROFILES, DOMAIN, PLATFORMS
from .manager import YunmaiScaleManager
from .models import YunmaiProfile

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Yunmai Scale from a config entry."""
    profile_values = entry.options.get(CONF_PROFILES, entry.data[CONF_PROFILES])
    profiles = [YunmaiProfile.from_dict(value) for value in profile_values]

    manager = YunmaiScaleManager(
        hass=hass,
        entry=entry,
        address=entry.data[CONF_ADDRESS],
        device_name=entry.data[CONF_DEVICE_NAME],
        profiles=profiles,
    )
    await manager.async_load()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await manager.async_start()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Yunmai Scale config entry."""
    manager: YunmaiScaleManager = hass.data[DOMAIN][entry.entry_id]
    _LOGGER.debug(
        "Unloading Yunmai config entry %s: state=%s",
        entry.entry_id,
        entry.state,
    )
    await manager.async_stop(reason="config_entry_unload")

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded


async def async_migrate_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Migrate legacy entries.

    Version 1 stored a fixed numeric age and version 2 stored a full birth
    date. Both remain supported. New profiles store only a birth year.
    """
    if entry.version > 3:
        return False

    if entry.version in {1, 2}:
        hass.config_entries.async_update_entry(entry, version=3)

    return True
