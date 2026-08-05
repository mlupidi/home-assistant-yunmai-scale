"""Persistent Bluetooth connection manager for Yunmai scales."""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import UTC, datetime
import logging
import re
from statistics import median
from typing import Any

from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .ble_power import apply_connection_parameters
from .const import (
    BLE_DEVICE_WAIT_SECONDS,
    BLE_POWER_MGMT_TIMEOUT_SECONDS,
    BLE_POWER_MODE_CUSTOM,
    BLE_POWER_MODE_OFF,
    BLE_POWER_MODES,
    BLE_POWER_PRESETS,
    BOOTSTRAP_SETTLE_SECONDS,
    CONF_BLE_POWER_INTERVAL_MS,
    CONF_BLE_POWER_LATENCY,
    CONF_BLE_POWER_MODE,
    CONF_BLE_POWER_OPTIMIZATION,
    CONF_BLE_POWER_SUPERVISION_TIMEOUT_S,
    CONF_MAX_RELATIVE_DIFFERENCE,
    CONF_MAX_STABLE_SPREAD_KG,
    CONF_MIN_SECOND_BEST_MARGIN_KG,
    CONF_STABLE_FRAMES,
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
    DUPLICATE_FINAL_WINDOW_SECONDS,
    FALLBACK_AVAILABILITY_SECONDS,
    LIVE_CYCLE_GAP_SECONDS,
    MAGIC_START,
    MEASUREMENT_TIMEOUT_SECONDS,
    MIN_HUMAN_WEIGHT_KG,
    POST_FINAL_GUARD_SECONDS,
    RECONNECT_DELAYS_SECONDS,
    STORAGE_KEY_PREFIX,
    STORAGE_VERSION,
    UUID_FFE4,
    UUID_FFE9,
)
from .models import ParsedFrame, YunmaiMeasurement, YunmaiProfile
from .protocol import build_time_packet, build_user_packet, parse_frame

_LOGGER = logging.getLogger(__name__)


class YunmaiScaleManager:
    """Keep one BLE connection open and process repeated weighings."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        address: str,
        device_name: str,
        profiles: list[YunmaiProfile],
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.address = address.upper()
        self.device_name = device_name
        self.profiles = profiles
        self.profiles_by_uid = {profile.uid: profile for profile in profiles}
        self.signal = f"{DOMAIN}_{entry.entry_id}_update"

        self.measurements: dict[int, YunmaiMeasurement] = {}
        self.last_user_uid: int | None = None
        self.status = "starting"
        self.last_error: str | None = None

        self._store = Store(
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY_PREFIX}.{entry.entry_id}",
        )
        self._unsubscribe = None
        self._connection_task: asyncio.Task[None] | None = None
        self._client: BleakClientWithServiceCache | None = None
        self._stop_event = asyncio.Event()
        self._advertisement_event = asyncio.Event()
        self._connection_generation = 0
        self._active_generation: int | None = None
        self._notification_callback_sequence = 0
        self.notification_session_id: int | None = None
        self.notification_callback_id: int | None = None
        self.notification_count = 0
        self.bluez_cache_reset_count = 0
        self.ble_power_status = "pending"
        self.ble_power_details: dict[str, Any] = {}

    @property
    def ble_power_mode(self) -> str:
        """Return the configured mode, including v0.3.2 migration."""
        mode = self.entry.options.get(CONF_BLE_POWER_MODE)
        if mode in BLE_POWER_MODES:
            return str(mode)
        enabled = bool(
            self.entry.options.get(
                CONF_BLE_POWER_OPTIMIZATION,
                DEFAULT_BLE_POWER_OPTIMIZATION,
            )
        )
        return DEFAULT_BLE_POWER_MODE if enabled else BLE_POWER_MODE_OFF

    @property
    def ble_power_optimization_enabled(self) -> bool:
        """Return whether local-BlueZ power optimization is enabled."""
        return self.ble_power_mode != BLE_POWER_MODE_OFF

    def _ble_power_parameters(self) -> tuple[int, int, int]:
        """Return interval, latency, and timeout in controller units."""
        mode = self.ble_power_mode
        if mode in BLE_POWER_PRESETS:
            return BLE_POWER_PRESETS[mode]
        if mode != BLE_POWER_MODE_CUSTOM:
            raise ValueError(f"Unsupported BLE power mode: {mode}")

        interval_ms = float(
            self.entry.options.get(
                CONF_BLE_POWER_INTERVAL_MS,
                DEFAULT_BLE_POWER_INTERVAL_MS,
            )
        )
        latency = int(
            self.entry.options.get(
                CONF_BLE_POWER_LATENCY,
                DEFAULT_BLE_POWER_LATENCY,
            )
        )
        timeout_s = float(
            self.entry.options.get(
                CONF_BLE_POWER_SUPERVISION_TIMEOUT_S,
                DEFAULT_BLE_POWER_SUPERVISION_TIMEOUT_S,
            )
        )
        return round(interval_ms / 1.25), latency, round(timeout_s * 100)

    @property
    def max_relative_difference(self) -> float:
        """Maximum relative difference from the user's reference weight."""
        return float(
            self.entry.options.get(
                CONF_MAX_RELATIVE_DIFFERENCE,
                DEFAULT_MAX_RELATIVE_DIFFERENCE,
            )
        )

    @property
    def min_second_best_margin_kg(self) -> float:
        """Minimum margin between the nearest and second-nearest user."""
        return float(
            self.entry.options.get(
                CONF_MIN_SECOND_BEST_MARGIN_KG,
                DEFAULT_MIN_SECOND_BEST_MARGIN_KG,
            )
        )

    @property
    def stable_frames(self) -> int:
        """Required count of consistent live-weight frames."""
        return int(self.entry.options.get(CONF_STABLE_FRAMES, DEFAULT_STABLE_FRAMES))

    @property
    def max_stable_spread_kg(self) -> float:
        """Maximum spread in the recognition window."""
        return float(
            self.entry.options.get(
                CONF_MAX_STABLE_SPREAD_KG,
                DEFAULT_MAX_STABLE_SPREAD_KG,
            )
        )

    async def async_load(self) -> None:
        """Load the latest measurements from storage."""
        stored = await self._store.async_load() or {}
        measurements = stored.get("measurements", {})
        for uid_text, value in measurements.items():
            try:
                uid = int(uid_text)
                if uid in self.profiles_by_uid:
                    self.measurements[uid] = YunmaiMeasurement.from_dict(value)
            except (KeyError, TypeError, ValueError):
                _LOGGER.warning(
                    "Ignoring invalid stored Yunmai measurement for %s", uid_text
                )

        last_uid = stored.get("last_user_uid")
        if isinstance(last_uid, int) and last_uid in self.profiles_by_uid:
            self.last_user_uid = last_uid

    async def async_start(self) -> None:
        """Start advertisement tracking and the persistent connection loop."""
        if self._connection_task is not None and not self._connection_task.done():
            _LOGGER.debug(
                "Yunmai persistent manager is already running for %s",
                self.address,
            )
            return
        bluetooth.async_set_fallback_availability_interval(
            self.hass,
            self.address,
            FALLBACK_AVAILABILITY_SECONDS,
        )

        self._stop_event.clear()
        self._advertisement_event.clear()

        self._unsubscribe = bluetooth.async_register_callback(
            self.hass,
            self._async_advertisement,
            {"address": self.address},
            bluetooth.BluetoothScanningMode.ACTIVE,
        )

        self._connection_task = self.entry.async_create_background_task(
            self.hass,
            self._async_connection_loop(),
            name=f"Yunmai persistent connection {self.address}",
        )
        _LOGGER.debug("Yunmai persistent manager started for %s", self.address)

    async def async_stop(self, *, reason: str = "unspecified") -> None:
        """Stop callbacks and close the persistent BLE connection."""
        _LOGGER.debug(
            "Stopping Yunmai manager for %s: reason=%s status=%s "
            "generation=%s connected=%s",
            self.address,
            reason,
            self.status,
            self._active_generation,
            bool(self._client and self._client.is_connected),
        )
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

        self._stop_event.set()
        self._advertisement_event.set()

        if self._connection_task is not None and not self._connection_task.done():
            self._connection_task.cancel()
            try:
                await self._connection_task
            except asyncio.CancelledError:
                pass
        self._connection_task = None
        self._client = None
        _LOGGER.debug(
            "Yunmai persistent manager stopped for %s: reason=%s",
            self.address,
            reason,
        )

    @callback
    def _async_advertisement(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Wake a reconnect attempt when the scale is observed."""
        _LOGGER.debug(
            "Yunmai advertisement: change=%s rssi=%s source=%s status=%s",
            change,
            getattr(service_info, "rssi", None),
            getattr(service_info, "source", None),
            self.status,
        )
        self._advertisement_event.set()

    def get_measurement(self, uid: int) -> YunmaiMeasurement | None:
        """Return the latest measurement for one profile."""
        return self.measurements.get(uid)

    def get_reference_weight(self, profile: YunmaiProfile) -> float:
        """Use the latest final weight, falling back to configured reference."""
        measurement = self.measurements.get(profile.uid)
        if measurement is not None:
            return measurement.weight_kg
        return profile.reference_weight

    def _set_status(self, status: str, error: str | None = None) -> None:
        """Update the diagnostic state and notify entities."""
        if self.status == status and self.last_error == error:
            return
        self.status = status
        self.last_error = error
        async_dispatcher_send(self.hass, self.signal)

    def _choose_profile(self, weight_kg: float) -> YunmaiProfile | None:
        """Return an unambiguous nearest profile for the live weight."""
        ranked = sorted(
            (
                (abs(weight_kg - self.get_reference_weight(profile)), profile)
                for profile in self.profiles
            ),
            key=lambda item: item[0],
        )
        if not ranked:
            return None

        best_difference, best_profile = ranked[0]
        allowed = self.get_reference_weight(best_profile) * self.max_relative_difference
        if best_difference > allowed:
            return None

        if len(ranked) > 1:
            second_difference = ranked[1][0]
            if second_difference - best_difference < self.min_second_best_margin_kg:
                return None

        return best_profile

    def _bootstrap_profile(self) -> YunmaiProfile:
        """Use the last measured user for bootstrap, otherwise the first profile."""
        if self.last_user_uid is not None:
            profile = self.profiles_by_uid.get(self.last_user_uid)
            if profile is not None:
                return profile
        return self.profiles[0]

    def _log_gatt_services(self, client: Any) -> None:
        """Log the discovered GATT table when a required characteristic is absent."""
        for service in client.services:
            _LOGGER.debug(
                "Yunmai GATT service %s handle=%s",
                service.uuid,
                service.handle,
            )
            for characteristic in service.characteristics:
                _LOGGER.debug(
                    "Yunmai GATT characteristic %s handle=%s properties=%s",
                    characteristic.uuid,
                    characteristic.handle,
                    ",".join(characteristic.properties),
                )

    async def _async_write(self, client, packet: bytes, label: str) -> None:
        """Write one command using the properties exposed by the GATT table."""
        characteristic = client.services.get_characteristic(UUID_FFE9)
        if characteristic is None:
            self._log_gatt_services(client)
            raise BleakError(
                "Required Yunmai write characteristic FFE9 is missing from "
                "the discovered GATT services; the BlueZ device cache may "
                "be incomplete"
            )

        properties = set(characteristic.properties)
        _LOGGER.debug("Yunmai TX %s: %s", label, packet.hex(" "))

        if "write" in properties:
            try:
                await client.write_gatt_char(
                    characteristic, packet, response=True
                )
                return
            except Exception as err:
                if "write-without-response" not in properties:
                    raise
                _LOGGER.debug(
                    "Yunmai TX %s write-with-response failed (%s); retrying "
                    "without response",
                    label,
                    err,
                )

        if "write-without-response" in properties:
            await client.write_gatt_char(
                characteristic, packet, response=False
            )
            return

        raise BleakError(
            "Yunmai FFE9 does not expose a supported write property: "
            f"{sorted(properties)}"
        )

    async def _async_send_profile(
        self,
        client,
        profile: YunmaiProfile,
        *,
        bootstrap: bool = False,
    ) -> None:
        """Send user, current time, and start commands."""
        prefix = "BOOT_" if bootstrap else ""
        if bootstrap:
            _LOGGER.debug(
                "Yunmai bootstrap profile %s; unit=kg",
                profile.name,
            )
        else:
            _LOGGER.debug(
                "Yunmai selected profile %s at reference %.2f kg",
                profile.name,
                self.get_reference_weight(profile),
            )

        await self._async_write(
            client,
            build_user_packet(profile, dt_util.now().date()),
            f"{prefix}SET_USER",
        )
        await self._async_write(client, build_time_packet(), f"{prefix}SET_TIME")
        await self._async_write(client, MAGIC_START, f"{prefix}MAGIC_START")

    async def _async_save_measurement(
        self,
        profile: YunmaiProfile,
        frame: ParsedFrame,
    ) -> None:
        """Persist one complete final measurement."""
        timestamp = frame.timestamp or datetime.now(tz=UTC)
        measurement = YunmaiMeasurement(
            weight_kg=float(frame.weight_kg),
            user_id=profile.uid,
            impedance_raw=int(frame.impedance_raw or 0),
            fat_percent=frame.fat_percent,
            timestamp=timestamp,
        )
        self.measurements[profile.uid] = measurement
        self.last_user_uid = profile.uid

        await self._store.async_save(
            {
                "last_user_uid": self.last_user_uid,
                "measurements": {
                    str(uid): item.to_dict() for uid, item in self.measurements.items()
                },
            }
        )
        async_dispatcher_send(self.hass, self.signal)

    async def _async_wait_for_ble_device(self):
        """Wait until Home Assistant has a connectable BLEDevice for the scale.

        Always check Home Assistant's current Bluetooth view before clearing and
        waiting on the local advertisement event.  This avoids losing an
        advertisement that arrived during reconnect backoff.
        """
        while not self._stop_event.is_set():
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass,
                self.address,
                connectable=True,
            )
            if ble_device is not None:
                return ble_device

            self._set_status("waiting_for_bluetooth", self.last_error)
            self._advertisement_event.clear()

            # Close the race between the lookup above and Event.clear(): an
            # advertisement may have updated Home Assistant in that interval.
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass,
                self.address,
                connectable=True,
            )
            if ble_device is not None:
                return ble_device

            try:
                await asyncio.wait_for(
                    self._advertisement_event.wait(),
                    timeout=BLE_DEVICE_WAIT_SECONDS,
                )
            except asyncio.TimeoutError:
                continue

        raise asyncio.CancelledError

    @staticmethod
    def _bluez_adapter_index(ble_device: Any) -> int | None:
        """Return hciN for a local BlueZ BLEDevice, or None for a proxy."""
        details = getattr(ble_device, "details", None)
        if not isinstance(details, dict):
            return None
        path = details.get("path")
        if not isinstance(path, str):
            return None
        match = re.search(r"/org/bluez/hci(\d+)(?:/|$)", path)
        return int(match.group(1)) if match else None

    def _session_is_current(self, client: Any, generation: int) -> bool:
        """Return whether callbacks still belong to the active BLE session."""
        return (
            self._active_generation == generation
            and self._client is client
            and bool(getattr(client, "is_connected", False))
        )

    async def _async_apply_ble_power_optimization(
        self,
        *,
        client: Any,
        generation: int,
        adapter_index: int | None,
    ) -> None:
        """Apply per-device Linux/BlueZ parameters without blocking HA."""
        if not self.ble_power_optimization_enabled:
            self.ble_power_status = "disabled"
            self.ble_power_details = {}
            return

        if adapter_index is None:
            self.ble_power_status = "unsupported_adapter"
            self.ble_power_details = {}
            _LOGGER.info(
                "Yunmai BLE power optimization skipped: connection is not "
                "through a local BlueZ adapter"
            )
            return

        if not self._session_is_current(client, generation):
            raise BleakError("Yunmai session changed before power optimization")

        self.ble_power_status = "applying"
        try:
            interval_units, latency, timeout_units = (
                self._ble_power_parameters()
            )
            applied = await asyncio.to_thread(
                apply_connection_parameters,
                controller_index=adapter_index,
                address=self.address,
                interval_units=interval_units,
                latency=latency,
                supervision_timeout_units=timeout_units,
                timeout_seconds=BLE_POWER_MGMT_TIMEOUT_SECONDS,
            )
        except Exception as err:  # The optimization must never break weighing.
            self.ble_power_status = "failed"
            self.ble_power_details = {"error": str(err)}
            _LOGGER.warning(
                "Yunmai BLE power optimization failed; continuing with "
                "controller defaults: %s",
                err,
            )
            return

        if not self._session_is_current(client, generation):
            raise BleakError("Yunmai session changed during power optimization")

        self.ble_power_status = "applied"
        self.ble_power_details = {
            "mode": self.ble_power_mode,
            "adapter": f"hci{applied.controller_index}",
            "address_type": applied.address_type,
            "interval_ms": applied.interval_ms,
            "latency": applied.latency,
            "maximum_idle_interval_ms": applied.maximum_idle_interval_ms,
            "supervision_timeout_ms": applied.supervision_timeout_ms,
        }
        _LOGGER.info(
            "Yunmai BLE power optimization applied on hci%d: "
            "mode=%s interval=%.2f ms latency=%d "
            "idle_max=%.0f ms timeout=%d ms",
            applied.controller_index,
            self.ble_power_mode,
            applied.interval_ms,
            applied.latency,
            applied.maximum_idle_interval_ms,
            applied.supervision_timeout_ms,
        )

    async def _async_connection_loop(self) -> None:
        """Maintain one connection and isolate callbacks by session."""
        attempt = 0

        while not self._stop_event.is_set():
            client = None
            generation: int | None = None
            disconnected_event: asyncio.Event | None = None
            adapter_index: int | None = None
            try:
                ble_device = await self._async_wait_for_ble_device()
                adapter_index = self._bluez_adapter_index(ble_device)
                self._set_status("connecting" if attempt == 0 else "reconnecting")
                _LOGGER.debug(
                    "Connecting to Yunmai name=%s address=%s details=%r",
                    getattr(ble_device, "name", None),
                    getattr(ble_device, "address", None),
                    getattr(ble_device, "details", None),
                )
                self.ble_power_status = (
                    "pending" if self.ble_power_optimization_enabled else "disabled"
                )
                self.ble_power_details = {}

                self._connection_generation += 1
                generation = self._connection_generation
                disconnected_event = asyncio.Event()

                @callback
                def _session_disconnected(disconnected_client: Any) -> None:
                    if (
                        self._active_generation != generation
                        or self._client is not disconnected_client
                    ):
                        _LOGGER.debug(
                            "Ignoring disconnect callback from stale Yunmai "
                            "session %s",
                            generation,
                        )
                        return
                    _LOGGER.debug(
                        "Yunmai disconnected callback fired for session %s",
                        generation,
                    )
                    disconnected_event.set()

                client = await establish_connection(
                    BleakClientWithServiceCache,
                    ble_device,
                    name=self.device_name,
                    disconnected_callback=_session_disconnected,
                    max_attempts=2,
                    timeout=20.0,
                    use_services_cache=False,
                )
                self._client = client
                self._active_generation = generation
                if not client.is_connected:
                    raise BleakError("Bleak returned a disconnected Yunmai client")

                attempt = 0
                await self._async_connected_loop(
                    client,
                    generation=generation,
                    disconnected_event=disconnected_event,
                    adapter_index=adapter_index,
                )
                if not self._stop_event.is_set():
                    raise BleakError("Yunmai connection ended unexpectedly")

            except asyncio.CancelledError:
                raise
            except Exception as err:  # Backends expose several exception classes.
                error_text = str(err)
                if error_text == "Scale disconnected":
                    _LOGGER.info("Yunmai scale disconnected; reconnecting")
                else:
                    _LOGGER.warning("Yunmai persistent connection failed: %s", err)
                self._set_status("reconnecting", error_text)
            finally:
                await self._async_cleanup_client(client, generation=generation)
                if generation is not None and self._active_generation == generation:
                    self._active_generation = None
                if self._client is client:
                    self._client = None

            if self._stop_event.is_set():
                break

            delay = RECONNECT_DELAYS_SECONDS[
                min(attempt, len(RECONNECT_DELAYS_SECONDS) - 1)
            ]
            attempt += 1
            _LOGGER.debug("Retrying Yunmai connection in %.1f seconds", delay)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass

    async def _async_cleanup_client(
        self, client: Any, *, generation: int | None
    ) -> None:
        """Best-effort cleanup of one concrete BLE client instance."""
        if client is None:
            return

        connected = bool(getattr(client, "is_connected", False))
        _LOGGER.debug(
            "Cleaning up Yunmai BLE client: session=%s connected=%s",
            generation,
            connected,
        )

        if connected:
            try:
                async with asyncio.timeout(2.0):
                    await client.stop_notify(UUID_FFE4)
                _LOGGER.debug(
                    "Stopped Yunmai FFE4 notifications for session %s",
                    generation,
                )
            except TimeoutError:
                _LOGGER.debug(
                    "Timed out stopping Yunmai notifications for session %s",
                    generation,
                )
            except Exception as err:
                _LOGGER.debug(
                    "Stopping Yunmai notifications failed for session %s: %s",
                    generation,
                    err,
                )

        # Call disconnect even when Bleak already reports False.  The backend
        # may still have per-client notification resources to release.
        try:
            async with asyncio.timeout(4.0):
                await client.disconnect()
        except TimeoutError:
            _LOGGER.debug(
                "Timed out disconnecting Yunmai BLE client for session %s",
                generation,
            )
        except Exception as err:  # Backend-specific cleanup errors are diagnostic.
            _LOGGER.debug(
                "Yunmai BLE client disconnect failed for session %s: %s",
                generation,
                err,
            )

    async def _async_connected_loop(
        self,
        client,
        *,
        generation: int,
        disconnected_event: asyncio.Event,
        adapter_index: int | None,
    ) -> None:
        """Subscribe once, bootstrap once, then process repeated measurements."""
        notification_queue: asyncio.Queue[tuple[int, bytes]] = asyncio.Queue()
        self._notification_callback_sequence += 1
        callback_id = self._notification_callback_sequence
        notification_count = 0
        accepting_measurements = False
        measurement_seen_before_ready = False
        reject_cycle_until_final = False
        self.notification_session_id = generation
        self.notification_callback_id = callback_id
        self.notification_count = 0

        selected_profile: YunmaiProfile | None = None
        candidate_profile: YunmaiProfile | None = None
        candidate_weights: deque[float] = deque(maxlen=max(2, self.stable_frames))
        cycle_started_at: float | None = None
        last_live_at: float | None = None
        ignore_live_until = 0.0
        last_final_signature: tuple[Any, ...] | None = None
        last_final_at = 0.0

        def _notification_callback(_sender: Any, data: bytearray) -> None:
            nonlocal notification_count
            nonlocal measurement_seen_before_ready
            if (
                self._active_generation != generation
                or self._client is not client
            ):
                _LOGGER.debug(
                    "Ignoring notification from stale Yunmai session %s "
                    "callback %s",
                    generation,
                    callback_id,
                )
                return
            notification_count += 1
            self.notification_count = notification_count
            raw = bytes(data)
            if not accepting_measurements:
                early_frame = parse_frame(raw)
                if early_frame.kind in {"measuring", "measured"}:
                    measurement_seen_before_ready = True
            notification_queue.put_nowait((notification_count, raw))

        def _reset_cycle() -> None:
            nonlocal selected_profile
            nonlocal candidate_profile
            nonlocal cycle_started_at
            nonlocal last_live_at
            selected_profile = None
            candidate_profile = None
            candidate_weights.clear()
            cycle_started_at = None
            last_live_at = None

        if not self._session_is_current(client, generation):
            raise BleakError("Yunmai session ended before notifications")

        if adapter_index is not None:
            await client.start_notify(
                UUID_FFE4,
                _notification_callback,
                bluez={"use_start_notify": False},
            )
        else:
            await client.start_notify(UUID_FFE4, _notification_callback)
        _LOGGER.debug(
            "Subscribed to persistent Yunmai FFE4 notifications: "
            "session=%s callback=%s",
            generation,
            callback_id,
        )
        await asyncio.sleep(BOOTSTRAP_SETTLE_SECONDS)

        if disconnected_event.is_set() or not self._session_is_current(
            client, generation
        ):
            raise BleakError("Scale disconnected during Yunmai bootstrap")

        await self._async_send_profile(
            client,
            self._bootstrap_profile(),
            bootstrap=True,
        )

        if disconnected_event.is_set() or not self._session_is_current(
            client, generation
        ):
            raise BleakError("Scale disconnected after Yunmai bootstrap")

        await self._async_apply_ble_power_optimization(
            client=client,
            generation=generation,
            adapter_index=adapter_index,
        )

        if disconnected_event.is_set() or not self._session_is_current(
            client, generation
        ):
            raise BleakError("Scale disconnected before Yunmai ready state")

        self._set_status("ready")
        accepting_measurements = True
        reject_cycle_until_final = measurement_seen_before_ready
        if reject_cycle_until_final:
            _LOGGER.info(
                "Yunmai measurement began before the connection reached ready; "
                "ignoring this complete measurement cycle"
            )
        _LOGGER.info("Yunmai persistent connection is ready")

        loop = asyncio.get_running_loop()

        while not self._stop_event.is_set():
            if (
                disconnected_event.is_set()
                or not self._session_is_current(client, generation)
            ):
                raise BleakError("Scale disconnected")

            now = loop.time()
            if (
                cycle_started_at is not None
                and now - cycle_started_at >= MEASUREMENT_TIMEOUT_SECONDS
            ):
                _LOGGER.info(
                    "Yunmai incomplete measurement timed out; remaining connected"
                )
                _reset_cycle()
                reject_cycle_until_final = False
                self._set_status("ready")

            try:
                frame_count, raw = await asyncio.wait_for(
                    notification_queue.get(), timeout=0.5
                )
            except asyncio.TimeoutError:
                continue

            frame = parse_frame(raw)
            _LOGGER.debug(
                "Yunmai RX: session=%s callback=%s count=%s kind=%s frame=%s",
                generation,
                callback_id,
                frame_count,
                frame.kind,
                raw.hex(" "),
            )
            now = loop.time()

            if reject_cycle_until_final:
                if frame.kind == "measuring" and frame.weight_kg is not None:
                    if frame.weight_kg >= MIN_HUMAN_WEIGHT_KG:
                        if cycle_started_at is None:
                            cycle_started_at = now
                            self._set_status("measuring")
                        last_live_at = now
                    continue
                if frame.kind == "measured":
                    last_final_signature = (
                        frame.user_id,
                        frame.weight_kg,
                        frame.impedance_raw,
                        frame.fat_percent,
                    )
                    last_final_at = now
                    _LOGGER.info(
                        "Ignored Yunmai final frame because this measurement "
                        "started during reconnect/bootstrap"
                    )
                    reject_cycle_until_final = False
                    _reset_cycle()
                    ignore_live_until = now + POST_FINAL_GUARD_SECONDS
                    self._set_status("ready")
                    continue

            if frame.kind == "measuring" and frame.weight_kg is not None:
                if frame.weight_kg < MIN_HUMAN_WEIGHT_KG or now < ignore_live_until:
                    continue

                if last_live_at is not None and now - last_live_at > LIVE_CYCLE_GAP_SECONDS:
                    _reset_cycle()
                last_live_at = now

                if cycle_started_at is None:
                    cycle_started_at = now
                    self._set_status("measuring")

                if selected_profile is not None:
                    continue

                profile = self._choose_profile(frame.weight_kg)
                if profile is None:
                    candidate_profile = None
                    candidate_weights.clear()
                    continue

                if candidate_profile is None or candidate_profile.uid != profile.uid:
                    candidate_profile = profile
                    candidate_weights.clear()

                candidate_weights.append(frame.weight_kg)
                if len(candidate_weights) < self.stable_frames:
                    continue

                spread = max(candidate_weights) - min(candidate_weights)
                if spread > self.max_stable_spread_kg:
                    continue

                selected_profile = profile
                stable_weight = median(candidate_weights)
                _LOGGER.info(
                    "Recognized %s from %.2f kg live plateau (spread %.2f kg)",
                    profile.name,
                    stable_weight,
                    spread,
                )
                await self._async_send_profile(client, profile)
                continue

            if frame.kind != "measured" or frame.weight_kg is None:
                continue

            signature = (
                frame.user_id,
                frame.weight_kg,
                frame.impedance_raw,
                frame.fat_percent,
            )
            if (
                last_final_signature == signature
                and now - last_final_at <= DUPLICATE_FINAL_WINDOW_SECONDS
            ):
                _LOGGER.debug("Ignoring duplicate Yunmai final frame")
                continue

            last_final_signature = signature
            last_final_at = now

            if selected_profile is None:
                _LOGGER.info(
                    "Yunmai measurement ignored: no configured profile matched "
                    "the final weight %.2f kg",
                    frame.weight_kg,
                )
                _reset_cycle()
                ignore_live_until = now + POST_FINAL_GUARD_SECONDS
                self._set_status("ready")
                continue

            if frame.user_id != selected_profile.uid:
                _LOGGER.warning(
                    "Yunmai final user ID 0x%08X does not match selected "
                    "ID 0x%08X; result ignored",
                    frame.user_id or 0,
                    selected_profile.uid,
                )
                self.last_error = "Final user ID did not match selected profile"
                _reset_cycle()
                ignore_live_until = now + POST_FINAL_GUARD_SECONDS
                self._set_status("ready", self.last_error)
                continue

            await self._async_save_measurement(selected_profile, frame)
            _LOGGER.info(
                "Yunmai final: %s %.2f kg, fat=%s, impedance=%s",
                selected_profile.name,
                frame.weight_kg,
                frame.fat_percent,
                frame.impedance_raw,
            )
            _reset_cycle()
            ignore_live_until = now + POST_FINAL_GUARD_SECONDS
            self._set_status("ready")
