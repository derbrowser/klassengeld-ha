"""Binärsensor: Es gibt offene Zahlungsaufforderungen."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import KlassengeldConfigEntry
from .entity import KlassengeldEntity
from .sensor import payments_attr


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
        async_add_entities(KlassengeldPaymentDue(coordinator, k) for k in new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class KlassengeldPaymentDue(KlassengeldEntity, BinarySensorEntity):
    _attr_translation_key = "payment_due"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, student_key) -> None:
        super().__init__(coordinator, student_key, "payment_due")

    @property
    def is_on(self) -> bool | None:
        s = self.student
        return bool(s.open_payments) if s else None

    @property
    def extra_state_attributes(self):
        s = self.student
        return payments_attr(s) if s else None
