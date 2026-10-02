"""Sensoren: Kontostand, offener Betrag, Anzahl offener Zahlungen, nächste Frist."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import KlassengeldConfigEntry
from .const import CURRENCY
from .entity import KlassengeldEntity
from .parser import Student


def payments_attr(student: Student) -> dict[str, Any]:
    """Offene Zahlungen als Attribut-Liste (für Karten/Templates)."""
    return {
        "payments": [
            {
                "title": p.title,
                "due": p.due.isoformat() if p.due else None,
                "amount": p.amount,
            }
            for p in student.open_payments
        ]
    }


@dataclass(frozen=True, kw_only=True)
class KlassengeldSensorDescription(SensorEntityDescription):
    value_fn: Callable[[Student], Any]
    attrs_fn: Callable[[Student], dict[str, Any]] | None = None


def _open_amount(s: Student) -> float:
    return round(sum(p.amount or 0 for p in s.open_payments), 2)


def _next_due(s: Student) -> date | None:
    dues = [p.due for p in s.open_payments if p.due]
    return min(dues) if dues else None


SENSORS: tuple[KlassengeldSensorDescription, ...] = (
    KlassengeldSensorDescription(
        key="balance",
        translation_key="balance",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=CURRENCY,
        suggested_display_precision=2,
        value_fn=lambda s: s.balance,
    ),
    KlassengeldSensorDescription(
        key="open_amount",
        translation_key="open_amount",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY,
        suggested_display_precision=2,
        value_fn=_open_amount,
        attrs_fn=payments_attr,
    ),
    KlassengeldSensorDescription(
        key="open_count",
        translation_key="open_count",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: len(s.open_payments),
        attrs_fn=payments_attr,
    ),
    KlassengeldSensorDescription(
        key="next_due",
        translation_key="next_due",
        device_class=SensorDeviceClass.DATE,
        value_fn=_next_due,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KlassengeldConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    known: set[str] = set()

    def _add_new() -> None:
        new = [k for k in coordinator.data if k not in known]
        if not new:
            return
        known.update(new)
        async_add_entities(
            KlassengeldSensor(coordinator, key, desc)
            for key in new
            for desc in SENSORS
        )

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class KlassengeldSensor(KlassengeldEntity, SensorEntity):
    entity_description: KlassengeldSensorDescription

    def __init__(self, coordinator, student_key, description) -> None:
        super().__init__(coordinator, student_key, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        s = self.student
        return self.entity_description.value_fn(s) if s else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        s = self.student
        fn = self.entity_description.attrs_fn
        return fn(s) if s and fn else None
