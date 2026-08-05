"""Sensor entities for Yunmai Scale."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfMass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .manager import YunmaiScaleManager
from .models import YunmaiProfile


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities) -> None:
    """Set up Yunmai sensor entities."""
    manager: YunmaiScaleManager = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        YunmaiStatusSensor(manager),
        YunmaiLastUserSensor(manager),
    ]

    for profile in manager.profiles:
        entities.extend(
            (
                YunmaiProfileSensor(manager, profile, "weight"),
                YunmaiProfileSensor(manager, profile, "fat"),
                YunmaiProfileSensor(manager, profile, "impedance"),
                YunmaiProfileSensor(manager, profile, "timestamp"),
            )
        )

    async_add_entities(entities)


class YunmaiBaseSensor(SensorEntity):
    """Common Yunmai sensor implementation."""

    _attr_has_entity_name = True

    def __init__(self, manager: YunmaiScaleManager) -> None:
        self.manager = manager

    @property
    def device_info(self) -> DeviceInfo:
        """Return scale device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.manager.address)},
            name=self.manager.device_name,
            manufacturer="Yunmai",
            model="Bluetooth body scale",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to manager updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                self.manager.signal,
                self._handle_manager_update,
            )
        )

    @callback
    def _handle_manager_update(self) -> None:
        self.async_write_ha_state()


class YunmaiStatusSensor(YunmaiBaseSensor):
    """Current integration session status."""

    _attr_name = "Session status"
    _attr_icon = "mdi:scale-bathroom"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, manager: YunmaiScaleManager) -> None:
        super().__init__(manager)
        self._attr_unique_id = f"{manager.address}_status"

    @property
    def native_value(self) -> str:
        return self.manager.status

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attributes: dict[str, Any] = {
            "ble_power_optimization": (
                self.manager.ble_power_optimization_enabled
            ),
            "ble_power_mode": self.manager.ble_power_mode,
            "ble_power_status": self.manager.ble_power_status,
            "ble_session_id": self.manager.notification_session_id,
            "ble_callback_id": self.manager.notification_callback_id,
            "ble_notification_count": self.manager.notification_count,
            "bluez_cache_reset_count": self.manager.bluez_cache_reset_count,
        }
        attributes.update(self.manager.ble_power_details)
        if self.manager.last_error is not None:
            attributes["last_error"] = self.manager.last_error
        return attributes


class YunmaiLastUserSensor(YunmaiBaseSensor):
    """Last recognized user."""

    _attr_name = "Last user"
    _attr_icon = "mdi:account-check"

    def __init__(self, manager: YunmaiScaleManager) -> None:
        super().__init__(manager)
        self._attr_unique_id = f"{manager.address}_last_user"

    @property
    def native_value(self) -> str | None:
        if self.manager.last_user_uid is None:
            return None
        profile = self.manager.profiles_by_uid.get(self.manager.last_user_uid)
        return profile.name if profile is not None else None


class YunmaiProfileSensor(YunmaiBaseSensor):
    """One measurement sensor for one configured person."""

    def __init__(
        self,
        manager: YunmaiScaleManager,
        profile: YunmaiProfile,
        kind: str,
    ) -> None:
        super().__init__(manager)
        self.profile = profile
        self.kind = kind
        self._attr_unique_id = f"{manager.address}_{profile.uid}_{kind}"

        if kind == "weight":
            self._attr_name = f"{profile.name} weight"
            self._attr_device_class = SensorDeviceClass.WEIGHT
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = UnitOfMass.KILOGRAMS
            self._attr_suggested_display_precision = 2
            self._attr_icon = "mdi:weight-kilogram"
        elif kind == "fat":
            self._attr_name = f"{profile.name} body fat"
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_suggested_display_precision = 2
            self._attr_icon = "mdi:percent"
        elif kind == "impedance":
            self._attr_name = f"{profile.name} impedance raw"
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_icon = "mdi:resistor"
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
            self._attr_entity_registry_enabled_default = False
        else:
            self._attr_name = f"{profile.name} last measurement"
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
            self._attr_icon = "mdi:clock-outline"

    @property
    def native_value(self) -> float | int | datetime | None:
        measurement = self.manager.get_measurement(self.profile.uid)
        if measurement is None:
            return None
        if self.kind == "weight":
            return measurement.weight_kg
        if self.kind == "fat":
            return measurement.fat_percent
        if self.kind == "impedance":
            return measurement.impedance_raw
        return measurement.timestamp
