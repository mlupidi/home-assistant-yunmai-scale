"""Connection switch for Yunmai Scale.

Turning the switch off closes the BLE connection and stops advertisement
tracking, so the scale can sleep and save battery. Turning it on reconnects.
The last state is restored after a Home Assistant restart, so a schedule or
automation can keep the scale connected only during the hours it is used.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .manager import YunmaiScaleManager


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities) -> None:
    """Set up the Yunmai connection switch."""
    manager: YunmaiScaleManager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([YunmaiConnectionSwitch(manager)])


class YunmaiConnectionSwitch(SwitchEntity, RestoreEntity):
    """Enable or pause the BLE connection to the scale."""

    _attr_has_entity_name = True
    _attr_name = "Connection"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, manager: YunmaiScaleManager) -> None:
        self.manager = manager
        self._attr_unique_id = f"{manager.address}_connection"

    @property
    def device_info(self) -> DeviceInfo:
        """Return scale device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.manager.address)},
            name=self.manager.device_name,
            manufacturer="Yunmai",
            model="Bluetooth body scale",
        )

    @property
    def is_on(self) -> bool:
        """Return whether the BLE connection is enabled."""
        return self.manager.connection_enabled

    @property
    def icon(self) -> str:
        """Return an icon that shows whether the connection is paused."""
        if self.manager.connection_enabled:
            return "mdi:bluetooth-connect"
        return "mdi:bluetooth-off"

    async def async_added_to_hass(self) -> None:
        """Restore the last state and follow manager updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                self.manager.signal,
                self._handle_manager_update,
            )
        )
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state == STATE_OFF:
            await self.manager.async_set_connection_enabled(False)

    @callback
    def _handle_manager_update(self) -> None:
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the BLE connection."""
        await self.manager.async_set_connection_enabled(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Pause the BLE connection so the scale can sleep."""
        await self.manager.async_set_connection_enabled(False)
        self.async_write_ha_state()
