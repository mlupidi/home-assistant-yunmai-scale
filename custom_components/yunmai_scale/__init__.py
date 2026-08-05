"""Yunmai Scale integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_DEVICE_NAME,
    CONF_PROFILES,
    DOMAIN,
    PLATFORMS,
    PROFILE_SENSOR_KINDS,
)
from .manager import YunmaiScaleManager
from .models import YunmaiProfile

_LOGGER = logging.getLogger(__name__)


@callback
def _async_remove_stale_profile_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    address: str,
    profiles: list[YunmaiProfile],
) -> None:
    """Remove registry entities belonging to profiles that no longer exist."""
    active_unique_ids = {
        f"{address}_{profile.uid}_{kind}"
        for profile in profiles
        for kind in PROFILE_SENSOR_KINDS
    }
    prefix = f"{address}_"
    registry = er.async_get(hass)
    removed: list[str] = []

    for registry_entry in er.async_entries_for_config_entry(
        registry, entry.entry_id
    ):
        unique_id = registry_entry.unique_id
        if registry_entry.platform != DOMAIN or not unique_id.startswith(prefix):
            continue

        is_profile_entity = False
        for kind in PROFILE_SENSOR_KINDS:
            suffix = f"_{kind}"
            if not unique_id.endswith(suffix):
                continue
            uid_text = unique_id[len(prefix) : -len(suffix)]
            is_profile_entity = uid_text.isdigit()
            break

        if not is_profile_entity or unique_id in active_unique_ids:
            continue

        removed.append(registry_entry.entity_id)
        registry.async_remove(registry_entry.entity_id)

    if removed:
        _LOGGER.info(
            "Removed stale Yunmai profile entities: %s",
            ", ".join(sorted(removed)),
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Yunmai Scale from a config entry."""
    profile_values = entry.options.get(CONF_PROFILES, entry.data[CONF_PROFILES])
    profiles = [YunmaiProfile.from_dict(value) for value in profile_values]
    _async_remove_stale_profile_entities(
        hass, entry, entry.data[CONF_ADDRESS], profiles
    )

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
