"""Yunmai BLE protocol helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime
import time

from .const import MAGIC_START
from .models import ParsedFrame, YunmaiProfile


def xor_checksum(packet: bytes) -> int:
    """Calculate Yunmai XOR checksum over bytes 1..last-1."""
    value = 0
    for byte in packet[1:-1]:
        value ^= byte
    return value


def checksum_ok(packet: bytes) -> bool:
    """Return whether a packet checksum is valid."""
    return len(packet) >= 3 and xor_checksum(packet) == packet[-1]


def _with_checksum(packet_without_checksum: bytes) -> bytes:
    packet = bytearray(packet_without_checksum + b"\x00")
    packet[-1] = xor_checksum(packet)
    return bytes(packet)


def build_user_packet(profile: YunmaiProfile, today: date) -> bytes:
    """Build SET_USER packet using the current age."""
    uid_hi = (profile.uid >> 8) & 0xFF
    uid_lo = profile.uid & 0xFF
    sex = 0x01 if profile.sex == "male" else 0x02
    activity = 0x01 if profile.activity else 0x00
    age = profile.age_on(today)
    if not 10 <= age <= 120:
        raise ValueError(f"Profile age {age} is outside the supported range")

    body = bytes(
        (
            0x0D,
            0x12,
            0x10,
            0x01,
            0x00,
            0x00,
            uid_hi,
            uid_lo,
            profile.height_cm,
            sex,
            age,
            0x55,
            0x5A,
            0x00,
            0x00,
            0x01,  # kilograms
            activity,
        )
    )
    return _with_checksum(body)


def build_time_packet() -> bytes:
    """Build SET_TIME packet using Unix time, big-endian."""
    unix_time = int(time.time()).to_bytes(4, "big", signed=False)
    body = bytes((0x0D, 0x0D, 0x11)) + unix_time + bytes(5)
    return _with_checksum(body)


def parse_frame(data: bytes) -> ParsedFrame:
    """Parse a Yunmai FFE4 notification."""
    if len(data) < 4 or data[0] != 0x0D or not checksum_ok(data):
        return ParsedFrame("invalid")

    response_type = data[3]

    if response_type == 0x01 and len(data) >= 11:
        return ParsedFrame(
            kind="measuring",
            weight_kg=int.from_bytes(data[8:10], "big") / 100.0,
        )

    if response_type == 0x02 and len(data) >= 18:
        unix_time = int.from_bytes(data[5:9], "big")
        try:
            timestamp = datetime.fromtimestamp(unix_time, tz=UTC)
        except (OverflowError, OSError, ValueError):
            timestamp = datetime.now(tz=UTC)

        fat_percent: float | None = None
        if len(data) >= 20 and data[1] >= 0x1E:
            fat_percent = int.from_bytes(data[17:19], "big") / 100.0

        return ParsedFrame(
            kind="measured",
            weight_kg=int.from_bytes(data[13:15], "big") / 100.0,
            user_id=int.from_bytes(data[9:13], "big"),
            impedance_raw=int.from_bytes(data[15:17], "big"),
            fat_percent=fat_percent,
            timestamp=timestamp,
        )

    return ParsedFrame(kind=f"response_{response_type:02x}")


__all__ = [
    "MAGIC_START",
    "build_time_packet",
    "build_user_packet",
    "checksum_ok",
    "parse_frame",
]
