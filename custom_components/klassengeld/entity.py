"""Gemeinsame Basis-Entität (ein Gerät pro Kind)."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import KlassengeldCoordinator
from .parser import Student


class KlassengeldEntity(CoordinatorEntity[KlassengeldCoordinator]):
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: KlassengeldCoordinator, student_key: str, kind: str
    ) -> None:
        super().__init__(coordinator)
        self._student_key = student_key
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{student_key}_{kind}"
        student = coordinator.data[student_key]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{student_key}")},
            name=student.name,
            manufacturer="Klassengeld",
            model=student.school_class,
            configuration_url="https://klassengeld.app/dashboard",
        )

    @property
    def student(self) -> Student | None:
        return self.coordinator.data.get(self._student_key)

    @property
    def available(self) -> bool:
        return super().available and self.student is not None
