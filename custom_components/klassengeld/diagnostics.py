"""Diagnose-Download (Zugangsdaten werden entfernt)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from . import KlassengeldConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: KlassengeldConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), {CONF_USERNAME, CONF_PASSWORD}),
        "parsed": {
            key: {**asdict(s), "payments": [asdict(p) for p in s.payments]}
            for key, s in (coordinator.data or {}).items()
        },
        # Sichtbarer Seitentext, um den Parser bei Layoutänderungen anzupassen.
        # Enthält Namen – vor dem Weitergeben prüfen.
        "page_lines": coordinator.client.last_lines,
    }
