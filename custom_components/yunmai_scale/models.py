"""Data models for the Yunmai Scale integration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any


def calculate_age(birth_date: date, today: date) -> int:
    """Return exact age in complete years for legacy date profiles."""
    return today.year - birth_date.year - (
        (today.month, today.day) < (birth_date.month, birth_date.day)
    )


@dataclass(slots=True, frozen=True)
class YunmaiProfile:
    """A user profile sent to the scale."""

    name: str
    uid: int
    height_cm: int
    sex: str
    birth_year: int | None
    reference_weight: float
    activity: bool = False
    legacy_birth_date: date | None = None
    legacy_age: int | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "YunmaiProfile":
        """Create a profile from config entry data."""
        birth_year_value = value.get("birth_year")
        birth_year = (
            None if birth_year_value is None else int(birth_year_value)
        )

        birth_date_value = value.get("birth_date")
        legacy_birth_date: date | None = None
        if birth_date_value:
            legacy_birth_date = date.fromisoformat(
                str(birth_date_value)
            )

        legacy_age_value = value.get("age")
        legacy_age = (
            None
            if legacy_age_value is None
            else int(legacy_age_value)
        )

        return cls(
            name=str(value["profile_name"]),
            uid=int(value["uid"]),
            height_cm=int(value["height_cm"]),
            sex=str(value["sex"]),
            birth_year=birth_year,
            reference_weight=float(value["reference_weight"]),
            activity=bool(value.get("activity", False)),
            legacy_birth_date=legacy_birth_date,
            legacy_age=legacy_age,
        )

    def age_on(self, today: date) -> int:
        """Return the age value to send to the scale."""
        if self.birth_year is not None:
            # Only the year is known. This deliberately changes on
            # January 1 and can differ from exact age by at most 1 year.
            return today.year - self.birth_year
        if self.legacy_birth_date is not None:
            return calculate_age(self.legacy_birth_date, today)
        if self.legacy_age is not None:
            return self.legacy_age
        raise ValueError(
            f"Profile {self.name!r} has no birth year or age"
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to config-entry-safe data."""
        result: dict[str, Any] = {
            "profile_name": self.name,
            "uid": self.uid,
            "height_cm": self.height_cm,
            "sex": self.sex,
            "reference_weight": self.reference_weight,
            "activity": self.activity,
        }
        if self.birth_year is not None:
            result["birth_year"] = self.birth_year
        elif self.legacy_birth_date is not None:
            result["birth_date"] = (
                self.legacy_birth_date.isoformat()
            )
        elif self.legacy_age is not None:
            result["age"] = self.legacy_age
        return result


@dataclass(slots=True)
class YunmaiMeasurement:
    """A final measurement received from the scale."""

    weight_kg: float
    user_id: int
    impedance_raw: int
    fat_percent: float | None
    timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        """Convert to storage data."""
        value = asdict(self)
        value["timestamp"] = self.timestamp.isoformat()
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "YunmaiMeasurement":
        """Restore a measurement from storage."""
        return cls(
            weight_kg=float(value["weight_kg"]),
            user_id=int(value["user_id"]),
            impedance_raw=int(value.get("impedance_raw", 0)),
            fat_percent=(
                None
                if value.get("fat_percent") is None
                else float(value["fat_percent"])
            ),
            timestamp=datetime.fromisoformat(
                str(value["timestamp"])
            ),
        )


@dataclass(slots=True)
class ParsedFrame:
    """Parsed Yunmai notification frame."""

    kind: str
    weight_kg: float | None = None
    user_id: int | None = None
    impedance_raw: int | None = None
    fat_percent: float | None = None
    timestamp: datetime | None = None
