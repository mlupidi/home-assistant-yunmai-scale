"""Config flow for Yunmai Scale."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv, selector
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ACTIVITY,
    BLE_POWER_MODE_CUSTOM,
    BLE_POWER_MODE_MAXIMUM,
    BLE_POWER_MODE_MODERATE,
    BLE_POWER_MODE_OFF,
    BLE_POWER_MODES,
    CONF_BLE_POWER_INTERVAL_MS,
    CONF_BLE_POWER_LATENCY,
    CONF_BLE_POWER_MODE,
    CONF_BLE_POWER_OPTIMIZATION,
    CONF_BLE_POWER_SUPERVISION_TIMEOUT_S,
    CONF_BIRTH_YEAR,
    CONF_DEVICE_NAME,
    CONF_HEIGHT_CM,
    CONF_MAX_RELATIVE_DIFFERENCE,
    CONF_MAX_STABLE_SPREAD_KG,
    CONF_MIN_SECOND_BEST_MARGIN_KG,
    CONF_PROFILE_NAME,
    CONF_PROFILES,
    CONF_REFERENCE_WEIGHT,
    CONF_SEX,
    CONF_STABLE_FRAMES,
    CONF_UID,
    DEFAULT_BLE_POWER_INTERVAL_MS,
    DEFAULT_BLE_POWER_LATENCY,
    DEFAULT_BLE_POWER_MODE,
    DEFAULT_BLE_POWER_OPTIMIZATION,
    DEFAULT_BLE_POWER_SUPERVISION_TIMEOUT_S,
    DEFAULT_MAX_RELATIVE_DIFFERENCE,
    DEFAULT_MAX_STABLE_SPREAD_KG,
    DEFAULT_MIN_SECOND_BEST_MARGIN_KG,
    DEFAULT_STABLE_FRAMES,
    DOMAIN,
    MAX_PROFILES,
    SUPPORTED_NAME_PREFIXES,
)

def _is_supported_name(name: str) -> bool:
    return any(name.startswith(prefix) for prefix in SUPPORTED_NAME_PREFIXES)


def _new_uid(existing_profiles: list[dict[str, Any]]) -> int:
    """Allocate a persistent Yunmai user ID from the verified safe range.

    IDs with bit 15 set were observed to be ignored by the scale, which then
    returned user ID 0 in the final frame.  The 0x1001..0x7FFF range keeps the
    high bit clear and includes IDs verified during profile-switch testing.
    """
    used = {int(profile[CONF_UID]) for profile in existing_profiles}
    for uid in range(0x1001, 0x8000):
        if uid not in used:
            return uid
    raise ValueError("No free Yunmai profile IDs remain in the safe range")


def _number_box(
    minimum: float,
    maximum: float,
    step: float,
    unit: str | None = None,
) -> selector.NumberSelector:
    """Return a numeric text-box selector."""
    config = selector.NumberSelectorConfig(
        min=minimum,
        max=maximum,
        step=step,
        mode=selector.NumberSelectorMode.BOX,
    )
    if unit is not None:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(config)


def _profile_schema(
    defaults: dict[str, Any] | None = None,
) -> vol.Schema:
    """Return the add/edit profile form, optionally prefilled."""
    current_year = dt_util.now().year
    values = defaults or {}

    birth_year = values.get(CONF_BIRTH_YEAR)
    if birth_year is None and values.get("birth_date"):
        birth_year = int(str(values["birth_date"])[:4])
    if birth_year is None and values.get("age") is not None:
        birth_year = current_year - int(values["age"])

    schema: dict[Any, Any] = {}

    name_default = values.get(CONF_PROFILE_NAME)
    name_key = (
        vol.Required(CONF_PROFILE_NAME, default=str(name_default))
        if name_default is not None
        else vol.Required(CONF_PROFILE_NAME)
    )
    schema[name_key] = selector.TextSelector()

    height_default = values.get(CONF_HEIGHT_CM)
    height_key = (
        vol.Required(CONF_HEIGHT_CM, default=int(height_default))
        if height_default is not None
        else vol.Required(CONF_HEIGHT_CM)
    )
    schema[height_key] = _number_box(100, 230, 1, "cm")

    schema[
        vol.Required(
            CONF_SEX,
            default=str(values.get(CONF_SEX, "male")),
        )
    ] = vol.In({"male": "Male", "female": "Female"})

    birth_year_key = (
        vol.Required(CONF_BIRTH_YEAR, default=int(birth_year))
        if birth_year is not None
        else vol.Required(CONF_BIRTH_YEAR)
    )
    schema[birth_year_key] = _number_box(
        current_year - 120,
        current_year - 10,
        1,
    )

    weight_default = values.get(CONF_REFERENCE_WEIGHT)
    weight_key = (
        vol.Required(
            CONF_REFERENCE_WEIGHT,
            default=float(weight_default),
        )
        if weight_default is not None
        else vol.Required(CONF_REFERENCE_WEIGHT)
    )
    schema[weight_key] = _number_box(20, 300, 0.1, "kg")

    schema[
        vol.Optional(
            CONF_ACTIVITY,
            default=bool(values.get(CONF_ACTIVITY, False)),
        )
    ] = selector.BooleanSelector()

    return vol.Schema(schema)


def _profile_from_input(
    user_input: dict[str, Any],
    existing_profiles: list[dict[str, Any]],
    *,
    existing_uid: int | None = None,
) -> tuple[dict[str, Any] | None, dict[str, str]]:
    """Validate and convert one profile form.

    When ``existing_uid`` is supplied the profile is being edited and its
    stable Yunmai user ID is preserved.
    """
    errors: dict[str, str] = {}
    name = str(user_input[CONF_PROFILE_NAME]).strip()

    if not name:
        errors[CONF_PROFILE_NAME] = "name_required"
    elif any(
        int(profile[CONF_UID]) != existing_uid
        and profile[CONF_PROFILE_NAME].casefold() == name.casefold()
        for profile in existing_profiles
    ):
        errors[CONF_PROFILE_NAME] = "duplicate_name"

    try:
        birth_year = int(float(user_input[CONF_BIRTH_YEAR]))
        age = dt_util.now().year - birth_year
        if not 10 <= age <= 120:
            errors[CONF_BIRTH_YEAR] = "invalid_birth_year"
    except (TypeError, ValueError):
        errors[CONF_BIRTH_YEAR] = "invalid_birth_year"

    if errors:
        return None, errors

    uid = (
        existing_uid
        if existing_uid is not None
        else _new_uid(existing_profiles)
    )

    return (
        {
            CONF_PROFILE_NAME: name,
            CONF_UID: uid,
            CONF_HEIGHT_CM: int(float(user_input[CONF_HEIGHT_CM])),
            CONF_SEX: str(user_input[CONF_SEX]),
            CONF_BIRTH_YEAR: birth_year,
            CONF_REFERENCE_WEIGHT: float(
                user_input[CONF_REFERENCE_WEIGHT]
            ),
            CONF_ACTIVITY: bool(user_input.get(CONF_ACTIVITY, False)),
        },
        {},
    )

def _configured_ble_power_mode(options: dict[str, Any]) -> str:
    """Return the current mode, migrating the v0.3.2 boolean in memory."""
    mode = options.get(CONF_BLE_POWER_MODE)
    if mode in BLE_POWER_MODES:
        return str(mode)
    enabled = bool(
        options.get(
            CONF_BLE_POWER_OPTIMIZATION,
            DEFAULT_BLE_POWER_OPTIMIZATION,
        )
    )
    return DEFAULT_BLE_POWER_MODE if enabled else BLE_POWER_MODE_OFF


def _validate_custom_ble_power(
    user_input: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, str]]:
    """Validate and normalize custom BLE connection parameters."""
    errors: dict[str, str] = {}
    try:
        interval_ms = float(user_input[CONF_BLE_POWER_INTERVAL_MS])
        latency_value = float(user_input[CONF_BLE_POWER_LATENCY])
        latency = int(latency_value)
        timeout_s = float(
            user_input[CONF_BLE_POWER_SUPERVISION_TIMEOUT_S]
        )
    except (KeyError, TypeError, ValueError):
        return None, {"base": "invalid_ble_parameters"}

    interval_units = round(interval_ms / 1.25)
    normalized_interval_ms = interval_units * 1.25
    if (
        not 7.5 <= interval_ms <= 4000.0
        or abs(normalized_interval_ms - interval_ms) > 0.001
    ):
        errors[CONF_BLE_POWER_INTERVAL_MS] = "invalid_ble_interval"

    if (
        not 0 <= latency <= 499
        or abs(latency_value - latency) > 0.001
    ):
        errors[CONF_BLE_POWER_LATENCY] = "invalid_ble_latency"

    timeout_units = round(timeout_s * 100.0)
    normalized_timeout_s = timeout_units / 100.0
    if (
        not 0.10 <= timeout_s <= 32.0
        or abs(normalized_timeout_s - timeout_s) > 0.001
    ):
        errors[CONF_BLE_POWER_SUPERVISION_TIMEOUT_S] = (
            "invalid_ble_timeout"
        )

    if not errors and timeout_s * 1000.0 <= (
        2.0 * interval_ms * (latency + 1)
    ):
        errors[CONF_BLE_POWER_SUPERVISION_TIMEOUT_S] = (
            "ble_timeout_too_short"
        )

    if errors:
        return None, errors

    return (
        {
            CONF_BLE_POWER_INTERVAL_MS: normalized_interval_ms,
            CONF_BLE_POWER_LATENCY: latency,
            CONF_BLE_POWER_SUPERVISION_TIMEOUT_S: normalized_timeout_s,
        },
        {},
    )


class YunmaiScaleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Yunmai Scale config flow."""

    VERSION = 3

    def __init__(self) -> None:
        self._address: str | None = None
        self._device_name = "Yunmai Scale"
        self._profiles: list[dict[str, Any]] = []

    async def async_step_bluetooth(
        self,
        discovery_info: bluetooth.BluetoothServiceInfoBleak,
    ):
        """Handle Bluetooth discovery."""
        name = discovery_info.name or discovery_info.address
        if not discovery_info.connectable or not _is_supported_name(name):
            return self.async_abort(reason="not_supported")

        self._address = discovery_info.address.upper()
        self._device_name = name
        await self.async_set_unique_id(self._address)
        self._abort_if_unique_id_configured()
        self.context["title_placeholders"] = {"name": name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(self, user_input=None):
        """Confirm a discovered scale."""
        if user_input is not None:
            return await self.async_step_profile()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._device_name},
        )

    async def async_step_user(self, user_input=None):
        """Allow manual setup from discovered Bluetooth devices."""
        discovered: dict[str, str] = {}
        for info in bluetooth.async_discovered_service_info(
            self.hass, connectable=True
        ):
            name = info.name or info.address
            if _is_supported_name(name):
                discovered[info.address.upper()] = (
                    f"{name} ({info.address.upper()})"
                )

        if user_input is not None:
            address = str(user_input[CONF_ADDRESS]).upper()
            self._address = address
            self._device_name = discovered.get(
                address, "Yunmai Scale"
            ).split(" (")[0]
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()
            return await self.async_step_profile()

        address_validator: Any = (
            vol.In(discovered) if discovered else cv.string
        )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_ADDRESS): address_validator}
            ),
        )

    async def async_step_profile(self, user_input=None):
        """Collect one recognition profile."""
        errors: dict[str, str] = {}
        if user_input is not None:
            profile, errors = _profile_from_input(
                user_input, self._profiles
            )
            if profile is not None:
                self._profiles.append(profile)

                if len(self._profiles) >= MAX_PROFILES:
                    return self._async_create_scale_entry()

                return await self.async_step_profile_saved()

        return self.async_show_form(
            step_id="profile",
            data_schema=_profile_schema(),
            errors=errors,
            description_placeholders={
                "number": str(len(self._profiles) + 1),
                "maximum": str(MAX_PROFILES),
            },
        )

    async def async_step_profile_saved(self, user_input=None):
        """Show actions after a profile has been saved."""
        profile = self._profiles[-1]
        return self.async_show_menu(
            step_id="profile_saved",
            menu_options={
                "add_profile": "Add another profile",
                "finish_setup": "Finish setup",
            },
            description_placeholders={
                "name": profile[CONF_PROFILE_NAME],
                "count": str(len(self._profiles)),
            },
        )

    async def async_step_add_profile(self, user_input=None):
        """Add another recognition profile."""
        return await self.async_step_profile()

    async def async_step_finish_setup(self, user_input=None):
        """Finish setup after one or more profiles were added."""
        return self._async_create_scale_entry()

    @callback
    def _async_create_scale_entry(self):
        """Create the config entry from the collected profiles."""
        assert self._address is not None
        return self.async_create_entry(
            title=self._device_name,
            data={
                CONF_ADDRESS: self._address,
                CONF_DEVICE_NAME: self._device_name,
                CONF_PROFILES: self._profiles,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return YunmaiScaleOptionsFlow()


class YunmaiScaleOptionsFlow(config_entries.OptionsFlowWithReload):
    """Manage recognition, profiles, and Bluetooth power settings."""

    _PROFILE_SELECTION = "profile_uid"
    def __init__(self) -> None:
        self._selected_profile_uid: int | None = None

    def _current_profiles(self) -> list[dict[str, Any]]:
        """Return writable copies of the currently configured profiles."""
        source = self.config_entry.options.get(
            CONF_PROFILES,
            self.config_entry.data[CONF_PROFILES],
        )
        return [dict(profile) for profile in source]

    def _profile_choices(self) -> dict[str, str]:
        """Return stable UID choices with useful human-readable labels."""
        return {
            str(int(profile[CONF_UID])): (
                f"{profile[CONF_PROFILE_NAME]} — "
                f"{float(profile[CONF_REFERENCE_WEIGHT]):.2f} kg"
            )
            for profile in self._current_profiles()
        }

    def _selected_profile(self) -> dict[str, Any] | None:
        """Return the profile selected by the previous flow step."""
        if self._selected_profile_uid is None:
            return None
        return next(
            (
                profile
                for profile in self._current_profiles()
                if int(profile[CONF_UID]) == self._selected_profile_uid
            ),
            None,
        )

    @callback
    def _async_save_profiles(self, profiles: list[dict[str, Any]]):
        """Save a complete profile list while preserving unrelated options."""
        new_options = dict(self.config_entry.options)
        new_options[CONF_PROFILES] = profiles
        return self.async_create_entry(title="", data=new_options)

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "bluetooth_power",
                "recognition",
                "profiles",
            ],
        )

    async def async_step_back(self, user_input=None):
        """Return from a submenu to the main options menu."""
        self._selected_profile_uid = None
        return await self.async_step_init()

    async def async_step_profiles(self, user_input=None):
        """Show profile-management actions without replacing the list."""
        profiles = self._current_profiles()
        menu_options: list[str] = []
        if len(profiles) < MAX_PROFILES:
            menu_options.append("profiles_add")
        if profiles:
            menu_options.append("profiles_edit_select")
        if len(profiles) > 1:
            menu_options.append("profiles_delete_select")
        menu_options.append("back")

        return self.async_show_menu(
            step_id="profiles",
            menu_options=menu_options,
            description_placeholders={
                "count": str(len(profiles)),
                "maximum": str(MAX_PROFILES),
            },
        )

    async def async_step_profiles_add(self, user_input=None):
        """Add one profile while preserving all existing profiles and UIDs."""
        profiles = self._current_profiles()
        errors: dict[str, str] = {}

        if user_input is not None:
            profile, errors = _profile_from_input(user_input, profiles)
            if profile is not None:
                profiles.append(profile)
                return self._async_save_profiles(profiles)

        return self.async_show_form(
            step_id="profiles_add",
            data_schema=_profile_schema(),
            errors=errors,
            description_placeholders={
                "number": str(len(profiles) + 1),
                "maximum": str(MAX_PROFILES),
            },
        )

    async def async_step_profiles_edit_select(self, user_input=None):
        """Select the profile to edit."""
        if user_input is not None:
            selection = str(user_input[self._PROFILE_SELECTION])
            self._selected_profile_uid = int(selection)
            return await self.async_step_profiles_edit()

        return self.async_show_form(
            step_id="profiles_edit_select",
            data_schema=vol.Schema(
                {
                    vol.Required(self._PROFILE_SELECTION): vol.In(
                        self._profile_choices()
                    )
                }
            ),
        )

    async def async_step_profiles_edit(self, user_input=None):
        """Edit one profile while preserving its stable Yunmai UID."""
        selected = self._selected_profile()
        if selected is None:
            return await self.async_step_profiles()

        profiles = self._current_profiles()
        selected_uid = int(selected[CONF_UID])
        errors: dict[str, str] = {}

        if user_input is not None:
            updated, errors = _profile_from_input(
                user_input,
                profiles,
                existing_uid=selected_uid,
            )
            if updated is not None:
                profiles = [
                    updated
                    if int(profile[CONF_UID]) == selected_uid
                    else profile
                    for profile in profiles
                ]
                return self._async_save_profiles(profiles)

        return self.async_show_form(
            step_id="profiles_edit",
            data_schema=_profile_schema(selected),
            errors=errors,
            description_placeholders={
                "name": str(selected[CONF_PROFILE_NAME])
            },
        )

    async def async_step_profiles_delete_select(self, user_input=None):
        """Select the profile to delete."""
        if user_input is not None:
            selection = str(user_input[self._PROFILE_SELECTION])
            self._selected_profile_uid = int(selection)
            return await self.async_step_profiles_delete_confirm()

        return self.async_show_form(
            step_id="profiles_delete_select",
            data_schema=vol.Schema(
                {
                    vol.Required(self._PROFILE_SELECTION): vol.In(
                        self._profile_choices()
                    )
                }
            ),
        )

    async def async_step_profiles_delete_confirm(self, user_input=None):
        """Delete the selected profile after explicit confirmation."""
        selected = self._selected_profile()
        if selected is None:
            return await self.async_step_profiles()

        if user_input is not None:
            selected_uid = int(selected[CONF_UID])
            profiles = [
                profile
                for profile in self._current_profiles()
                if int(profile[CONF_UID]) != selected_uid
            ]
            # Keep at least one profile so recognition and bootstrap remain
            # well-defined even if a flow is invoked directly.
            if profiles:
                return self._async_save_profiles(profiles)
            return await self.async_step_profiles()

        return self.async_show_form(
            step_id="profiles_delete_confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "name": str(selected[CONF_PROFILE_NAME]),
                "weight": f"{float(selected[CONF_REFERENCE_WEIGHT]):.2f}",
            },
        )

    async def async_step_bluetooth_power(self, user_input=None):
        """Select a disabled, preset, or custom power mode."""
        current = dict(self.config_entry.options)
        current_mode = _configured_ble_power_mode(current)

        if user_input is not None:
            mode = str(user_input[CONF_BLE_POWER_MODE])
            if mode == BLE_POWER_MODE_CUSTOM:
                return await self.async_step_bluetooth_power_custom()

            new_options = dict(current)
            new_options[CONF_BLE_POWER_MODE] = mode
            new_options[CONF_BLE_POWER_OPTIMIZATION] = (
                mode != BLE_POWER_MODE_OFF
            )
            return self.async_create_entry(title="", data=new_options)

        return self.async_show_form(
            step_id="bluetooth_power",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_BLE_POWER_MODE,
                        default=current_mode,
                    ): vol.In(
                        {
                            BLE_POWER_MODE_OFF: "Disabled",
                            BLE_POWER_MODE_MODERATE: (
                                "Moderate — 45 ms / latency 9 / "
                                "idle up to 450 ms"
                            ),
                            BLE_POWER_MODE_MAXIMUM: (
                                "Maximum tested — 45 ms / latency 19 / "
                                "idle up to 900 ms"
                            ),
                            BLE_POWER_MODE_CUSTOM: "Custom parameters",
                        }
                    ),
                }
            ),
        )

    async def async_step_bluetooth_power_custom(self, user_input=None):
        """Configure validated custom local-BlueZ parameters."""
        current = dict(self.config_entry.options)
        errors: dict[str, str] = {}

        if user_input is not None:
            normalized, errors = _validate_custom_ble_power(user_input)
            if normalized is not None:
                new_options = dict(current)
                new_options[CONF_BLE_POWER_MODE] = BLE_POWER_MODE_CUSTOM
                new_options[CONF_BLE_POWER_OPTIMIZATION] = True
                new_options.update(normalized)
                return self.async_create_entry(title="", data=new_options)

        return self.async_show_form(
            step_id="bluetooth_power_custom",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_BLE_POWER_INTERVAL_MS,
                        default=current.get(
                            CONF_BLE_POWER_INTERVAL_MS,
                            DEFAULT_BLE_POWER_INTERVAL_MS,
                        ),
                    ): _number_box(7.5, 4000.0, 1.25, "ms"),
                    vol.Required(
                        CONF_BLE_POWER_LATENCY,
                        default=current.get(
                            CONF_BLE_POWER_LATENCY,
                            DEFAULT_BLE_POWER_LATENCY,
                        ),
                    ): _number_box(0, 499, 1),
                    vol.Required(
                        CONF_BLE_POWER_SUPERVISION_TIMEOUT_S,
                        default=current.get(
                            CONF_BLE_POWER_SUPERVISION_TIMEOUT_S,
                            DEFAULT_BLE_POWER_SUPERVISION_TIMEOUT_S,
                        ),
                    ): _number_box(0.1, 32.0, 0.1, "s"),
                }
            ),
            errors=errors,
        )

    async def async_step_recognition(self, user_input=None):
        if user_input is not None:
            new_options = dict(self.config_entry.options)
            new_options.update(user_input)
            return self.async_create_entry(title="", data=new_options)

        current = self.config_entry.options
        return self.async_show_form(
            step_id="recognition",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_MAX_RELATIVE_DIFFERENCE,
                        default=current.get(
                            CONF_MAX_RELATIVE_DIFFERENCE,
                            DEFAULT_MAX_RELATIVE_DIFFERENCE,
                        ),
                    ): _number_box(0.01, 0.50, 0.01),
                    vol.Required(
                        CONF_MIN_SECOND_BEST_MARGIN_KG,
                        default=current.get(
                            CONF_MIN_SECOND_BEST_MARGIN_KG,
                            DEFAULT_MIN_SECOND_BEST_MARGIN_KG,
                        ),
                    ): _number_box(0.0, 30.0, 0.1, "kg"),
                    vol.Required(
                        CONF_STABLE_FRAMES,
                        default=current.get(
                            CONF_STABLE_FRAMES,
                            DEFAULT_STABLE_FRAMES,
                        ),
                    ): _number_box(2, 10, 1),
                    vol.Required(
                        CONF_MAX_STABLE_SPREAD_KG,
                        default=current.get(
                            CONF_MAX_STABLE_SPREAD_KG,
                            DEFAULT_MAX_STABLE_SPREAD_KG,
                        ),
                    ): _number_box(0.1, 5.0, 0.1, "kg"),
                }
            ),
        )
