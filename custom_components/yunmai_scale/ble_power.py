"""Optional per-device BlueZ connection parameter optimization.

This module intentionally uses the Linux Bluetooth Management control socket
instead of changing controller-wide defaults.  Every request is scoped to one
controller index and one connected LE identity address.
"""

from __future__ import annotations

from dataclasses import dataclass
import socket
import struct
import time

MGMT_OP_GET_CONNECTIONS = 0x0015
MGMT_OP_LOAD_CONN_PARAM = 0x0035
MGMT_EV_CMD_COMPLETE = 0x0001
MGMT_EV_CMD_STATUS = 0x0002

HCI_DEV_NONE = 0xFFFF


class BluetoothPowerOptimizationError(RuntimeError):
    """Raised when BlueZ rejects or cannot apply the requested parameters."""


@dataclass(frozen=True, slots=True)
class AppliedConnectionParameters:
    """Connection parameters accepted by the Linux Bluetooth stack."""

    controller_index: int
    address_type: int
    interval_units: int
    latency: int
    supervision_timeout_units: int

    @property
    def interval_ms(self) -> float:
        return self.interval_units * 1.25

    @property
    def maximum_idle_interval_ms(self) -> float:
        return self.interval_ms * (self.latency + 1)

    @property
    def supervision_timeout_ms(self) -> int:
        return self.supervision_timeout_units * 10


def _address_to_mgmt(address: str) -> bytes:
    """Convert conventional MAC notation to little-endian bdaddr_t bytes."""
    compact = address.replace(":", "")
    if len(compact) != 12:
        raise BluetoothPowerOptimizationError(
            f"Invalid Bluetooth address: {address}"
        )
    try:
        return bytes.fromhex(compact)[::-1]
    except ValueError as err:
        raise BluetoothPowerOptimizationError(
            f"Invalid Bluetooth address: {address}"
        ) from err


def _format_address(raw: bytes) -> str:
    return ":".join(f"{byte:02X}" for byte in reversed(raw))


def _status_text(status: int) -> str:
    names = {
        0x00: "Success",
        0x01: "Unknown Command",
        0x03: "Failed",
        0x07: "No Resources",
        0x0A: "Busy",
        0x0B: "Rejected",
        0x0C: "Not Supported",
        0x0D: "Invalid Parameters",
        0x0F: "Not Powered",
        0x11: "Invalid Index",
        0x14: "Permission Denied",
    }
    return names.get(status, "Unknown")


def _send_command(
    sock: socket.socket,
    *,
    opcode: int,
    controller_index: int,
    parameters: bytes = b"",
    timeout_seconds: float,
) -> bytes:
    """Send one Management command and return its command-complete payload."""
    packet = struct.pack(
        "<HHH", opcode, controller_index, len(parameters)
    ) + parameters
    sock.send(packet)

    deadline = time.monotonic() + timeout_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise BluetoothPowerOptimizationError(
                f"Timed out waiting for BlueZ MGMT opcode 0x{opcode:04X}"
            )
        sock.settimeout(remaining)
        try:
            raw = sock.recv(4096)
        except TimeoutError as err:
            raise BluetoothPowerOptimizationError(
                f"Timed out waiting for BlueZ MGMT opcode 0x{opcode:04X}"
            ) from err

        if len(raw) < 6:
            continue
        event, event_index, payload_length = struct.unpack_from("<HHH", raw, 0)
        payload = raw[6 : 6 + payload_length]
        if event_index != controller_index:
            continue

        if event == MGMT_EV_CMD_COMPLETE and len(payload) >= 3:
            completed_opcode, status = struct.unpack_from("<HB", payload, 0)
            if completed_opcode != opcode:
                continue
            if status != 0:
                raise BluetoothPowerOptimizationError(
                    f"BlueZ MGMT opcode 0x{opcode:04X} failed: "
                    f"0x{status:02X} ({_status_text(status)})"
                )
            return payload[3:]

        if event == MGMT_EV_CMD_STATUS and len(payload) >= 3:
            status = payload[0]
            status_opcode = struct.unpack_from("<H", payload, 1)[0]
            if status_opcode != opcode:
                continue
            if status != 0:
                raise BluetoothPowerOptimizationError(
                    f"BlueZ MGMT opcode 0x{opcode:04X} failed: "
                    f"0x{status:02X} ({_status_text(status)})"
                )
            # A successful Command Status normally precedes a later completion.


def _get_connected_address_type(
    sock: socket.socket,
    *,
    controller_index: int,
    address: str,
    timeout_seconds: float,
) -> int:
    """Return the LE address type for one currently connected peer."""
    result = _send_command(
        sock,
        opcode=MGMT_OP_GET_CONNECTIONS,
        controller_index=controller_index,
        timeout_seconds=timeout_seconds,
    )
    if len(result) < 2:
        raise BluetoothPowerOptimizationError(
            "Malformed BlueZ Get Connections response"
        )

    count = struct.unpack_from("<H", result, 0)[0]
    offset = 2
    wanted = address.upper()
    for _ in range(count):
        entry = result[offset : offset + 7]
        if len(entry) != 7:
            raise BluetoothPowerOptimizationError(
                "Truncated BlueZ Get Connections response"
            )
        current_address = _format_address(entry[:6])
        address_type = entry[6]
        if current_address == wanted:
            if address_type not in (0x01, 0x02):
                raise BluetoothPowerOptimizationError(
                    f"Connected Yunmai address has unsupported type {address_type}"
                )
            return address_type
        offset += 7

    raise BluetoothPowerOptimizationError(
        f"{address} is not listed as connected on hci{controller_index}"
    )


def _load_parameters(
    sock: socket.socket,
    *,
    controller_index: int,
    address: str,
    address_type: int,
    interval_units: int,
    latency: int,
    supervision_timeout_units: int,
    timeout_seconds: float,
) -> None:
    parameters = struct.pack(
        "<H6sBHHHH",
        1,
        _address_to_mgmt(address),
        address_type,
        interval_units,
        interval_units,
        latency,
        supervision_timeout_units,
    )
    _send_command(
        sock,
        opcode=MGMT_OP_LOAD_CONN_PARAM,
        controller_index=controller_index,
        parameters=parameters,
        timeout_seconds=timeout_seconds,
    )


def apply_connection_parameters(
    *,
    controller_index: int,
    address: str,
    interval_units: int,
    latency: int,
    supervision_timeout_units: int,
    timeout_seconds: float = 5.0,
) -> AppliedConnectionParameters:
    """Apply per-device parameters to the currently connected Yunmai scale.

    The kernel retains a per-device parameter record after a disconnect, but a
    newly created explicit GATT connection may still start with controller
    defaults.  Two safe timeout values are therefore loaded in sequence.  At
    least one differs from any retained record, forcing the kernel to issue a
    connection-parameter update for the live link.  The final record contains
    the requested timeout.
    """
    if not 6 <= interval_units <= 3200:
        raise BluetoothPowerOptimizationError("Invalid BLE interval")
    if not 0 <= latency <= 499:
        raise BluetoothPowerOptimizationError("Invalid BLE peripheral latency")
    if not 10 <= supervision_timeout_units <= 3200:
        raise BluetoothPowerOptimizationError("Invalid BLE supervision timeout")

    # Bluetooth Core validity condition, expressed in milliseconds.
    if supervision_timeout_units * 10 <= 2 * interval_units * 1.25 * (latency + 1):
        raise BluetoothPowerOptimizationError(
            "Supervision timeout is too short for the requested interval/latency"
        )

    try:
        af_bluetooth = socket.AF_BLUETOOTH
        btproto_hci = socket.BTPROTO_HCI
        hci_channel_control = socket.HCI_CHANNEL_CONTROL
    except AttributeError as err:
        raise BluetoothPowerOptimizationError(
            "Python does not expose the Linux Bluetooth Management socket"
        ) from err

    try:
        sock = socket.socket(af_bluetooth, socket.SOCK_RAW, btproto_hci)
        sock.bind((HCI_DEV_NONE, hci_channel_control))
    except OSError as err:
        raise BluetoothPowerOptimizationError(
            f"Cannot open the Linux Bluetooth Management socket: {err}"
        ) from err

    try:
        address_type = _get_connected_address_type(
            sock,
            controller_index=controller_index,
            address=address,
            timeout_seconds=timeout_seconds,
        )

        # Toggle only the supervision timeout, not the power-relevant interval
        # or latency.  This makes re-application reliable after every reconnect.
        temporary_timeout = (
            supervision_timeout_units - 10
            if supervision_timeout_units >= 20
            else supervision_timeout_units + 10
        )
        _load_parameters(
            sock,
            controller_index=controller_index,
            address=address,
            address_type=address_type,
            interval_units=interval_units,
            latency=latency,
            supervision_timeout_units=temporary_timeout,
            timeout_seconds=timeout_seconds,
        )
        time.sleep(1.0)
        _load_parameters(
            sock,
            controller_index=controller_index,
            address=address,
            address_type=address_type,
            interval_units=interval_units,
            latency=latency,
            supervision_timeout_units=supervision_timeout_units,
            timeout_seconds=timeout_seconds,
        )
    finally:
        sock.close()

    return AppliedConnectionParameters(
        controller_index=controller_index,
        address_type=address_type,
        interval_units=interval_units,
        latency=latency,
        supervision_timeout_units=supervision_timeout_units,
    )
